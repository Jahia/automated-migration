"""Engine-level integrity-belt wiring tests (verifier.run_integrity_belt +
verify_result integration).

The belt runs the read-only integrity probe as an ADDITIONAL verification after a
content step's own probes pass. These tests MOCK the subprocess (no live Jahia,
no network) and assert:
  (a) triggers on content steps only (task_type==content OR the known step ids);
  (b) skips gracefully when no site is derivable (audit note, verification stays
      passed — never crash);
  (c) a non-zero belt exit FAILS the verification (same path as any probe);
  (d) the ORCHESTRATOR_INTEGRITY kill-switch disables it;
  (e) site derivation prefers inputs.site, falls back to project basename;
  (f) the belt does NOT run when the step's own probes already failed.
"""
from __future__ import annotations

import asyncio

import pytest

from src.config import settings
from src.models import AgentResult, StepState
from src.verifier import (
    derive_site,
    integrity_command,
    is_content_phase,
    run_integrity_belt,
    verify_result,
)


def run_async(coro):
    return asyncio.run(coro)


class FakeProc:
    """Stand-in for an asyncio subprocess: canned returncode + streams."""

    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self._out = stdout
        self._err = stderr
        self.killed = False

    async def communicate(self):
        return self._out, self._err

    def kill(self):
        self.killed = True


def _content_step(step_id="step_content_load", task_type="content",
                  inputs=None, criteria=None):
    return StepState(
        id=step_id, story_id="s1", title="load", task_type=task_type,
        inputs=inputs if inputs is not None else {"project": "projects/demo", "site": "demosite"},
        acceptance_criteria=criteria if criteria is not None else ["PROBE: true"],
    )


def _ok_result(step_id="step_content_load"):
    return AgentResult(step_id=step_id, agent="code", status="completed", summary="done")


@pytest.fixture
def integrity_on(monkeypatch):
    monkeypatch.setattr(settings, "integrity", True)
    monkeypatch.setattr(settings, "integrity_timeout", 120.0)
    yield


# ── (a) content-phase gating ────────────────────────────────────────────
def test_is_content_phase_by_task_type():
    assert is_content_phase(_content_step(step_id="anything", task_type="content"))


def test_is_content_phase_by_step_id():
    # step_pages is task_type=build in gen_plan, but is a known content step id
    assert is_content_phase(_content_step(step_id="step_pages", task_type="build"))
    assert is_content_phase(_content_step(step_id="step_publish_parity", task_type="publish"))


def test_is_not_content_phase():
    assert not is_content_phase(_content_step(step_id="step_deploy", task_type="deploy"))
    assert not is_content_phase(_content_step(step_id="step_scaffold", task_type="build"))


def test_belt_skips_non_content_step(integrity_on, monkeypatch):
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("subprocess must not run for a non-content step")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _boom)
    step = _content_step(step_id="step_deploy", task_type="deploy")
    checks, errors = run_async(run_integrity_belt(step, "/tmp", run_id=None))
    assert called["n"] == 0
    assert errors == []
    assert checks == []  # not content-phase → belt is a no-op


# ── (b) graceful skip when no site derivable ────────────────────────────
def test_belt_skips_without_site(integrity_on, monkeypatch):
    async def _boom(*a, **k):
        raise AssertionError("subprocess must not run without a derivable site")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _boom)
    step = _content_step(inputs={})  # no project, no site
    checks, errors = run_async(run_integrity_belt(step, "/tmp", run_id=None))
    assert errors == []  # graceful: no crash, verification unaffected
    assert "integrity_skipped:no_site" in checks


# ── (c) belt failure fails the verification ──────────────────────────────
def test_belt_failure_fails_verification(integrity_on, monkeypatch):
    async def _fake_shell(cmd, **k):
        if "orchestration/probes/integrity.py" in cmd:
            return FakeProc(1, stdout=b"integrity belt\n  RESULT: 19 MISMATCH(es)")
        return FakeProc(0)  # the step's own PROBE: true passes → belt then runs

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)
    step = _content_step()
    result = _ok_result()
    vr = run_async(verify_result(step, result, "/tmp", run_id=None))
    assert vr.passed is False
    assert any("Integrity belt failed" in e for e in vr.errors)


def test_belt_pass_keeps_verification_passed(integrity_on, monkeypatch):
    async def _fake_shell(cmd, **k):
        if "integrity.py" in cmd:
            return FakeProc(0, stdout=b"CLEAN")
        return FakeProc(0)  # the step's own PROBE: true

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)
    step = _content_step()
    vr = run_async(verify_result(step, _ok_result(), "/tmp", run_id=None))
    assert vr.passed is True
    assert "integrity_passed" in vr.checks


# ── (d) kill-switch ──────────────────────────────────────────────────────
def test_kill_switch_disables_belt(monkeypatch):
    monkeypatch.setattr(settings, "integrity", False)

    async def _boom(*a, **k):
        raise AssertionError("subprocess must not run when integrity is disabled")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _boom)
    step = _content_step()
    checks, errors = run_async(run_integrity_belt(step, "/tmp", run_id=None))
    assert errors == []
    assert "integrity_disabled" in checks


# ── (e) site derivation + command shape ─────────────────────────────────
def test_derive_site_prefers_inputs_site():
    step = _content_step(inputs={"project": "projects/foo", "site": "explicitsite"})
    assert derive_site(step) == "explicitsite"


def test_derive_site_falls_back_to_project_basename():
    # the LIVE plan has no inputs.site — engine falls back to the basename
    step = _content_step(inputs={"project": "projects/discoverasr"})
    assert derive_site(step) == "discoverasr"


def test_derive_site_none_without_project():
    step = _content_step(inputs={})
    assert derive_site(step) is None


def test_integrity_command_shape():
    step = _content_step(step_id="step_pages",
                         inputs={"project": "projects/demo", "site": "demosite"})
    cmd = integrity_command(step)
    assert cmd == "python3 orchestration/probes/integrity.py projects/demo demosite --phase step_pages"


def test_integrity_command_none_without_project():
    assert integrity_command(_content_step(inputs={})) is None


# ── (f) belt does NOT run when the step's own probes failed ─────────────
def test_belt_not_run_when_own_probe_failed(integrity_on, monkeypatch):
    calls = {"integrity": 0}

    async def _fake_shell(cmd, **k):
        if "integrity.py" in cmd:
            calls["integrity"] += 1
            return FakeProc(0)
        return FakeProc(1, stderr=b"the step's own probe failed")  # PROBE: false

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)
    step = _content_step(criteria=["PROBE: false"])
    vr = run_async(verify_result(step, _ok_result(), "/tmp", run_id=None))
    assert vr.passed is False
    # the belt is skipped because the step's own gate already failed
    assert calls["integrity"] == 0


# ── (g) audit records the belt as a probe with the [integrity] marker ───
def test_belt_audited_with_integrity_marker(integrity_on, monkeypatch, tmp_path):
    recorded = []

    class FakeAudit:
        def probe_executed(self, **kw):
            recorded.append(kw)

    # the belt imports get_audit_logger lazily via `from .audit import ...`,
    # so patching the source module is the correct interception point.
    import src.audit as audit_mod
    monkeypatch.setattr(audit_mod, "get_audit_logger", lambda run_id: FakeAudit())

    async def _fake_shell(cmd, **k):
        return FakeProc(0, stdout=b"CLEAN")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)
    step = _content_step()
    run_async(run_integrity_belt(step, "/tmp", run_id="run123"))
    assert recorded, "belt must audit its execution"
    assert any("[integrity]" in r.get("command", "") for r in recorded)
