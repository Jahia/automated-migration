"""Engine-executes-Run: doctrine tests (P5).

A step whose acceptance_criteria carry `Run: <cmd>` lines has a KNOWN,
deterministic command at plan time. The engine runs those lines ITSELF (same
subprocess mechanism as the probes) BEFORE opening any agent session — so an LLM
never burns its 600s session deadline READING files to type a command the
planner already wrote (the step_content_load 2×600s DeepSeek read-loop incident).

Doctrine: the engine drives (P5.5b: DeepSeek left the control loop entirely — no
repair agent). A known command is not a decision point. These tests MOCK the
subprocess (no live tools, no network) and assert:
  (a) run_lines parses `Run:` / `Run[NNN]:` in order, ignoring PROBE: lines;
  (b) all Run: lines pass  → NO agent session opened, synthetic engine result,
      verification still runs (the probes/belt remain the judge);
  (c) a Run: line FAILS → the step FAILS with the failure context stashed on
      step.failure_context (retries re-run it; exhausted → decision_pending);
  (d) a timeout counts as a failure (exit -1, timeout message in context);
  (e) the ORCHESTRATOR_ENGINE_EXEC_RUN kill-switch restores the legacy path;
  (f) a step with NO Run: lines is unchanged (legacy agent path);
  (g) content steps get the long timeout, others the default;
  (h) each execution is audited as command_executed (mirror of probe_executed).
"""
from __future__ import annotations

import asyncio

import pytest

from src import orchestrator, persistence
from src.config import settings
from src.models import (
    AgentResult,
    EpicInput,
    PlanInput,
    StepInput,
    StepState,
    StepStatus,
    StoryInput,
    VerificationResult,
)
from src.prompt_builder import build_step_prompt
from src.state import build_run_state
from src.verifier import (
    is_content_task,
    run_lines,
    run_step_commands,
    run_step_timeout,
)


def run_async(coro):
    async def _wrap():
        try:
            return await coro
        finally:
            await persistence.close_db()
    return asyncio.run(_wrap())


class FakeProc:
    """Stand-in for an asyncio subprocess: canned returncode + streams. A
    per-call `hang` option lets a test drive the wait_for timeout path."""

    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"", hang: bool = False):
        self.returncode = returncode
        self._out = stdout
        self._err = stderr
        self.killed = False
        self._hang = hang

    async def communicate(self):
        # Hang only until killed: the production timeout path does
        # proc.kill(); await proc.communicate() to DRAIN — a real subprocess
        # returns promptly there, so the post-kill drain must not re-hang.
        if self._hang and not self.killed:
            await asyncio.sleep(3600)  # outlast any test timeout → wait_for fires
        return self._out, self._err

    def kill(self):
        self.killed = True


def _step(step_id="step_content_load", task_type="content", criteria=None):
    return StepState(
        id=step_id, story_id="s1", title="load", task_type=task_type,
        acceptance_criteria=criteria if criteria is not None else [
            "Run: python3 orchestration/lib/load_content.py demo demosite --clean",
            "PROBE: python3 orchestration/probes/contribution.py demo",
        ],
    )


@pytest.fixture
def exec_run_on(monkeypatch):
    monkeypatch.setattr(settings, "engine_exec_run", True)
    monkeypatch.setattr(settings, "engine_exec_run_content_timeout", 3600.0)
    monkeypatch.setattr(settings, "engine_exec_run_default_timeout", 900.0)
    yield


# ── (a) run_lines parsing ────────────────────────────────────────────────
def test_run_lines_parses_plain_and_ignores_probe():
    lines = run_lines([
        "Run: echo one",
        "PROBE: test -s foo",
        "Run: echo two",
    ])
    assert lines == [("echo one", None), ("echo two", None)]


def test_run_lines_timeout_override():
    lines = run_lines(["Run[120]: cold build here"])
    assert lines == [("cold build here", 120.0)]


def test_run_lines_collapses_whitespace_and_keeps_order():
    lines = run_lines(["Run:   python3   a.py    --flag", "Run: b.py"])
    assert lines == [("python3 a.py --flag", None), ("b.py", None)]


def test_run_lines_empty_when_none():
    assert run_lines(None) == []
    assert run_lines(["PROBE: test -s x"]) == []


# ── (g) timeout selection by task_type ───────────────────────────────────
def test_content_task_gets_long_timeout(exec_run_on):
    assert is_content_task(_step(task_type="content"))
    assert run_step_timeout(_step(task_type="content")) == 3600.0


def test_content_step_id_gets_long_timeout(exec_run_on):
    # step_pages is task_type=build in gen_plan but is a known content step id
    assert run_step_timeout(_step(step_id="step_pages", task_type="build")) == 3600.0


def test_non_content_gets_default_timeout(exec_run_on):
    assert run_step_timeout(_step(step_id="step_crawl", task_type="build")) == 900.0


# ── (b) all Run: lines pass → engine executes, records returned ──────────
def test_run_step_commands_all_pass(exec_run_on, monkeypatch):
    seen = []

    async def _fake_shell(cmd, **k):
        seen.append(cmd)
        return FakeProc(0, stdout=b"ok")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)
    step = _step(criteria=["Run: echo a", "Run: echo b", "PROBE: test true"])
    ok, records, ctx = run_async(run_step_commands(step, "/tmp", run_id=None))
    assert ok is True
    assert ctx == ""
    assert [r["command"] for r in records] == ["echo a", "echo b"]
    assert all(r["passed"] for r in records)
    assert seen == ["echo a", "echo b"]  # ran both, in order, PROBE excluded


# ── (c) a Run: line fails → stop, failure context built ──────────────────
def test_run_step_commands_stops_at_first_failure(exec_run_on, monkeypatch):
    seen = []

    async def _fake_shell(cmd, **k):
        seen.append(cmd)
        if cmd == "echo b":
            return FakeProc(2, stdout=b"partial out", stderr=b"boom traceback")
        return FakeProc(0)

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)
    step = _step(criteria=["Run: echo a", "Run: echo b", "Run: echo c"])
    ok, records, ctx = run_async(run_step_commands(step, "/tmp", run_id=None))
    assert ok is False
    assert seen == ["echo a", "echo b"]  # stopped BEFORE echo c
    assert records[-1]["exit_code"] == 2
    assert "echo b" in ctx
    assert "Exit code: 2" in ctx
    assert "boom traceback" in ctx  # stderr tail carried for the repairer
    assert "partial out" in ctx     # stdout tail too


# ── (d) timeout counts as failure ────────────────────────────────────────
def test_run_step_commands_timeout_is_failure(exec_run_on, monkeypatch):
    async def _fake_shell(cmd, **k):
        return FakeProc(0, hang=True)

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)
    # Run[1]: → 1s per-line override so the hanging proc trips wait_for fast.
    step = _step(criteria=["Run[1]: sleep forever"])
    ok, records, ctx = run_async(run_step_commands(step, "/tmp", run_id=None))
    assert ok is False
    assert records[0]["exit_code"] == -1
    assert "timed out" in ctx


# ── (e) kill-switch → no subprocess, legacy path ─────────────────────────
def test_kill_switch_disables_engine_exec(monkeypatch):
    monkeypatch.setattr(settings, "engine_exec_run", False)

    async def _boom(*a, **k):
        raise AssertionError("subprocess must not run when engine_exec_run is off")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _boom)
    ok, records, ctx = run_async(run_step_commands(_step(), "/tmp", run_id=None))
    assert ok is True and records == [] and ctx == ""


# ── (f) no Run: lines → no subprocess ────────────────────────────────────
def test_no_run_lines_is_noop(exec_run_on, monkeypatch):
    async def _boom(*a, **k):
        raise AssertionError("subprocess must not run without Run: lines")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _boom)
    step = _step(criteria=["PROBE: test -s x"])
    ok, records, ctx = run_async(run_step_commands(step, "/tmp", run_id=None))
    assert ok is True and records == [] and ctx == ""


# ── (h) audit records command_executed with the mirror shape ─────────────
def test_run_audited_as_command_executed(exec_run_on, monkeypatch):
    recorded = []

    class FakeAudit:
        def command_executed(self, **kw):
            recorded.append(kw)

    # run_step_commands binds get_audit_logger at module scope in verifier.
    monkeypatch.setattr("src.verifier.get_audit_logger", lambda run_id: FakeAudit())

    async def _fake_shell(cmd, **k):
        return FakeProc(0, stdout=b"x" * 5000, stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)
    step = _step(criteria=["Run: echo a"])
    run_async(run_step_commands(step, "/tmp", run_id="run123"))
    assert recorded, "engine-run command must be audited"
    r = recorded[0]
    assert r["command"] == "echo a"
    assert r["exit_code"] == 0
    assert r["step_id"] == step.id
    # FakeAudit replaces the whole method, so it sees the FULL stdout — the ~500c
    # truncation lives inside the real method body (asserted separately below).
    assert isinstance(r["stdout"], str)


def test_command_executed_audit_truncates_stdout(tmp_path):
    """The real logger writes stdout/stderr truncated to ~500c (mirror of the
    probe_executed 2000c truncation, tighter to keep the trail lean)."""
    import json

    from src.audit import RunAuditLogger

    logger = RunAuditLogger("run_trunc", log_dir=tmp_path)
    logger.command_executed(
        epic_id="", story_id="", step_id="step_x",
        command="c" * 400, exit_code=0,
        stdout="o" * 5000, stderr="e" * 5000, duration_ms=1.0)
    entry = json.loads((tmp_path / "run_trunc.jsonl").read_text().strip())
    assert entry["event"] == "command_executed"
    assert len(entry["stdout"]) == 500
    assert len(entry["stderr"]) == 500
    assert entry["passed"] is True


# ── prompt repair block ──────────────────────────────────────────────────
def _mini_run():
    plan = PlanInput(
        goal="g", repo_dir="/tmp",
        epics=[EpicInput(id="e1", title="E", goal="g", stories=[
            StoryInput(id="s1", title="S", description="d", steps=[
                StepInput(id="step_content_load", title="load", task_type="content",
                          acceptance_criteria=["Run: echo x", "PROBE: test true"]),
            ]),
        ])],
    )
    return build_run_state(plan)


def test_prompt_has_no_repair_block_by_default():
    run = _mini_run()
    epic = run.epics[0]
    story = epic.stories[0]
    step = story.steps[0]
    prompt = build_step_prompt(step, story, epic, run)
    assert "RÉPARATEUR" not in prompt


def test_prompt_includes_repair_block_when_run_failed():
    run = _mini_run()
    epic = run.epics[0]
    story = epic.stories[0]
    step = story.steps[0]
    ctx = "EXÉCUTION DÉTERMINISTE ÉCHOUÉE — le moteur ...\nCommande: echo x\nExit code: 2\n"
    prompt = build_step_prompt(step, story, epic, run, run_failure=ctx)
    assert "EXÉCUTION DÉTERMINISTE ÉCHOUÉE" in prompt
    assert "Exit code: 2" in prompt


# ── integration: _execute_single_step engine path ───────────────────────
# P5.5b: DeepSeek left the control loop — there is NO repair agent to monkeypatch.
# The engine either fabricates a synthetic "engine" result (Run: lines pass, or no
# Run: lines) and lets verification judge, or FAILS the step with failure_context
# when a Run: line fails. FakeClient is a bare LLMClient stand-in that is never
# touched: the engine makes no LLM calls.
class FakeClient:
    """LLMClient stand-in. model attr only; chat() is never reached — the engine
    makes NO LLM calls in the control loop (P5.5b)."""

    model = "deepseek-v4-flash"


def _patch_side_effects(monkeypatch):
    async def _noop_notify(*a, **k):
        return None

    async def _noop_save(*a, **k):
        return None

    monkeypatch.setattr(orchestrator, "notify_sse", _noop_notify)
    monkeypatch.setattr(orchestrator, "save_run", _noop_save)


def test_execute_single_step_engine_path_skips_agent(exec_run_on, monkeypatch):
    async def scenario():
        _patch_side_effects(monkeypatch)

        async def _fake_shell(cmd, **k):
            return FakeProc(0, stdout=b"done")

        monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)

        captured = {}

        async def _fake_verify(step, agent_result, repo_dir, run_id=None):
            captured["agent"] = agent_result.agent
            captured["summary"] = agent_result.summary
            return VerificationResult(passed=True, checks=["command_passed:echo x"], errors=[])

        monkeypatch.setattr(orchestrator, "verify_result", _fake_verify)

        run = _mini_run()
        run.run_id = "run_engine_path"
        orchestrator.register_run(run)
        epic = run.epics[0]
        story = epic.stories[0]
        step = story.steps[0]

        client = FakeClient()
        await orchestrator._execute_single_step(run, epic, story, step, client, None)

        # NO LLM invoked — the engine fabricates a synthetic result and verify judges
        assert step.status == StepStatus.done
        assert captured["agent"] == "engine"
        assert "echo x" in captured["summary"]

    run_async(scenario())


def test_execute_single_step_run_failure_fails_step_with_context(exec_run_on, monkeypatch):
    """P5.5b: a failing Run: line FAILS the step (no repair agent). The failure
    context (command / exit code / stderr tail) is stashed on step.failure_context
    for the decision bundle; verify_result is NEVER reached."""
    async def scenario():
        _patch_side_effects(monkeypatch)

        async def _fake_shell(cmd, **k):
            return FakeProc(1, stderr=b"engine ran it and it broke")

        monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)

        # verify must NOT be reached on a Run: failure
        async def _boom_verify(step, agent_result, repo_dir, run_id=None):
            raise AssertionError("verify must not run when a Run: line failed")

        monkeypatch.setattr(orchestrator, "verify_result", _boom_verify)

        run = _mini_run()
        run.run_id = "run_run_failure"
        orchestrator.register_run(run)
        epic = run.epics[0]
        story = epic.stories[0]
        step = story.steps[0]

        client = FakeClient()
        await orchestrator._execute_single_step(run, epic, story, step, client, None)

        assert step.status == StepStatus.failed  # NO repair agent — the step fails
        assert step.failure_context is not None
        assert "engine ran it and it broke" in step.failure_context
        assert "Exit code: 1" in step.failure_context

    run_async(scenario())


def test_execute_single_step_no_run_lines_synthesizes_engine_result(exec_run_on, monkeypatch):
    """A step with only PROBE: lines (no Run:) is NOT sent to any agent (P5.5b: the
    LLM left the loop). The engine fabricates a synthetic engine result and lets
    verification (the probes) judge — no subprocess, no LLM call."""
    async def scenario():
        _patch_side_effects(monkeypatch)

        async def _boom_shell(cmd, **k):
            raise AssertionError("engine must not exec: this step has no Run: lines")

        monkeypatch.setattr(asyncio, "create_subprocess_shell", _boom_shell)

        captured = {}

        async def _fake_verify(step, agent_result, repo_dir, run_id=None):
            captured["agent"] = agent_result.agent
            return VerificationResult(passed=True, checks=[], errors=[])

        monkeypatch.setattr(orchestrator, "verify_result", _fake_verify)

        plan = PlanInput(
            goal="g", repo_dir="/tmp",
            epics=[EpicInput(id="e1", title="E", goal="g", stories=[
                StoryInput(id="s1", title="S", description="d", steps=[
                    StepInput(id="step_probe_only", title="v", task_type="verify",
                              acceptance_criteria=["PROBE: test true"]),
                ]),
            ])],
        )
        run = build_run_state(plan)
        run.run_id = "run_probe_only"
        orchestrator.register_run(run)
        epic = run.epics[0]
        story = epic.stories[0]
        step = story.steps[0]

        client = FakeClient()
        await orchestrator._execute_single_step(run, epic, story, step, client, None)

        assert step.status == StepStatus.done  # engine synthetic result + verify passed
        assert captured["agent"] == "engine"  # NO LLM invoked

    run_async(scenario())
