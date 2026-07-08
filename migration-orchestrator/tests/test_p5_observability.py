"""P5 observability suite: expose truths the engine already records, stop it
lying (see MEMORY session-2026-07-08-p0-p1-observability.md).

Covers, one section per audit finding:
  1. GET /runs/{run_id}/events/history — additive, paginated, read-only view over
     the persisted `events` table (previously written by notify_sse/save_event,
     never read by any route). Lives at a DIFFERENT path than the existing SSE
     stream at GET /runs/{run_id}/events (routes/events.py) — that literal path
     is already taken, and renaming a live, frontend-consumed SSE endpoint would
     be a breaking change, not an additive one.
  2. completed_at honesty: StepState.completed_at/duration_ms must never be
     stamped while parking a NON-terminal decision_pending step
     (orchestrator._park_for_decision), and must be CLEARED (not left stale) the
     moment a step leaves a terminal state back to pending/ready — state.
     clear_execution_timing, wired into reset_steps_from, normalize_for_resume,
     orchestrator._reset_step (and therefore restart_run) and jump_to_step.
  3. Phantom 'running' runs: persistence._mark_interrupted_runs, a boot-time pass
     (init_tables, AFTER _migrate_runs_project) that flips any run stuck
     'running' with no live process to the new RunStatus.interrupted, stamping a
     trace note in state_json AND an events-table row. try_resume_run accepts
     'interrupted' so resumability is preserved.
  4. Audit JSONL relocated from /tmp/orch-audit to a persistent,
     package-anchored default (migration-orchestrator/logs/audit), overridable
     via ORCHESTRATOR_AUDIT_DIR (settings.audit_dir). Readers (routes/stats.py,
     orchestrator.decision_bundles, the new per-step log endpoint) fall back to
     the legacy path via audit.audit_log_path so pre-existing runs stay readable.
  5. GET /runs/{run_id}/steps/{step_id}/log — the captured stdout/stderr for a
     step ALREADY exists (probe_executed/command_executed entries in the per-run
     audit JSONL, written by verifier.py via audit.py) but was never exposed
     standalone; audit.read_step_audit_entries is the shared reader, also used
     to de-duplicate orchestrator.decision_bundles' own audit-file parsing.

Same style as test_decision_protocol.py / test_gate_integrity.py: drives the
state machine and orchestrator functions directly (no live engine). DB-backed
tests always point settings.db_path at a tmp file and close the connection
afterwards. Audit-log tests always monkeypatch audit.DEFAULT_AUDIT_DIR (and
audit.LEGACY_AUDIT_DIR where relevant) to a tmp dir — NEVER the real
migration-orchestrator/logs/audit or /tmp/orch-audit.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import aiosqlite
import pytest

from src import audit as audit_mod
from src import orchestrator, persistence
from src.config import settings
from src.models import (
    EpicInput,
    PlanInput,
    RunStatus,
    StepInput,
    StepState,
    StepStatus,
    StoryInput,
    StoryState,
)
from src.routes import runs as runs_routes
from src.routes import stats as stats_routes
from src.state import clear_execution_timing, normalize_for_resume, reset_steps_from


def run_async(coro):
    async def _wrap():
        try:
            return await coro
        finally:
            await persistence.close_db()
    return asyncio.run(_wrap())


def _plan(steps: list[StepInput]) -> PlanInput:
    return PlanInput(
        goal="test goal",
        repo_dir="/tmp",
        epics=[EpicInput(id="e1", title="Epic", goal="g", stories=[
            StoryInput(id="s1", title="Story", description="d", steps=steps),
        ])],
    )


def _build(run_id: str, steps: list[StepInput]):
    from src.state import build_run_state
    run = build_run_state(_plan(steps))
    run.run_id = run_id
    orchestrator.register_run(run)
    return run


async def _wait_for(predicate, timeout: float = 5.0):
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


def _runs_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(runs_routes.router)
    return TestClient(app)


# ── (1) GET /runs/{run_id}/events/history — persisted events, paginated ──────


def test_list_events_newest_first_and_scoped_to_run(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(settings, "db_path", str(tmp_path / "events.db"))
        for i in range(3):
            await persistence.save_event("run_ev", f"type_{i}", {"i": i})
        await persistence.save_event("run_other", "type_x", {})
        events = await persistence.list_events("run_ev", limit=10)
        assert [e["type"] for e in events] == ["type_2", "type_1", "type_0"]
        assert events[0]["payload"] == {"i": 2}
        assert await persistence.list_events("run_missing", limit=10) == []
    run_async(scenario())


def test_list_events_before_id_pagination_never_overlaps(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(settings, "db_path", str(tmp_path / "events_page.db"))
        for i in range(5):
            await persistence.save_event("run_page", f"t{i}", {})
        page1 = await persistence.list_events("run_page", limit=2)
        assert [e["type"] for e in page1] == ["t4", "t3"]
        page2 = await persistence.list_events("run_page", limit=2, before_id=page1[-1]["id"])
        assert [e["type"] for e in page2] == ["t2", "t1"]
        page3 = await persistence.list_events("run_page", limit=2, before_id=page2[-1]["id"])
        assert [e["type"] for e in page3] == ["t0"]
    run_async(scenario())


def test_events_history_route_shape_and_next_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "events_route.db"))

    async def seed():
        await persistence.save_event("run_hist", "step_status", {"status": "running"}, step_id="step_a")
        await persistence.save_event("run_hist", "step_status", {"status": "done"}, step_id="step_a")
        await persistence.close_db()
    asyncio.run(seed())

    run = SimpleNamespace(run_id="run_hist")
    monkeypatch.setattr(runs_routes, "get_run", lambda rid: run if rid == "run_hist" else None)
    try:
        resp = _runs_client().get("/runs/run_hist/events/history?limit=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == "run_hist"
        assert body["count"] == 1
        assert body["events"][0]["type"] == "step_status"
        assert body["events"][0]["payload"]["status"] == "done"  # newest first
        assert body["events"][0]["step_id"] == "step_a"
        assert body["next_before_id"] == body["events"][0]["id"]  # a full page → more may exist

        resp2 = _runs_client().get("/runs/run_hist/events/history?limit=50")
        assert resp2.json()["next_before_id"] is None  # short page → no more rows
    finally:
        asyncio.run(persistence.close_db())


def test_events_history_route_404_for_unknown_run(monkeypatch):
    monkeypatch.setattr(runs_routes, "get_run", lambda rid: None)

    async def _no_load(rid):
        return None
    monkeypatch.setattr(runs_routes, "load_run", _no_load)
    resp = _runs_client().get("/runs/ghost/events/history")
    assert resp.status_code == 404


def test_events_history_route_does_not_collide_with_sse_stream():
    """The existing GET /runs/{run_id}/events (routes/events.py) is the LIVE SSE
    stream — a different endpoint at a different path than events/history. This
    is a structural guard against accidentally re-adding a route at the exact
    SSE path, which would silently shadow it (Starlette matches by registration
    order)."""
    from src.routes import events as events_routes
    sse_paths = {r.path for r in events_routes.router.routes}
    history_paths = {r.path for r in runs_routes.router.routes}
    assert "/runs/{run_id}/events" in sse_paths
    assert "/runs/{run_id}/events" not in history_paths
    assert "/runs/{run_id}/events/history" in history_paths


# ── (2) completed_at honesty ──────────────────────────────────────────────


def test_clear_execution_timing_resets_all_three_fields():
    step = StepState(id="x", story_id="s1", started_at=1.0, completed_at=2.0, duration_ms=1.0)
    clear_execution_timing(step)
    assert step.started_at is None
    assert step.completed_at is None
    assert step.duration_ms is None


def test_reset_steps_from_clears_stale_timing():
    # reset_steps_from resets from_step_id AND every step AFTER it in list order
    # (the loop_to semantics) — use a single step so the assertion is unambiguous.
    story = StoryState(id="s1", title="S", description="d", steps=[
        StepState(id="a", story_id="s1", status=StepStatus.done,
                  started_at=1.0, completed_at=2.0, duration_ms=1.0),
    ])
    ids = reset_steps_from(story, "a")
    assert ids == ["a"]
    a = story.steps[0]
    assert a.status == StepStatus.pending
    assert a.started_at is None and a.completed_at is None and a.duration_ms is None


def test_normalize_for_resume_clears_stale_timing_on_recovered_steps():
    run = _build("run_test_normalize_timing", [
        StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
    ])
    step = run.epics[0].stories[0].steps[0]
    step.status = StepStatus.failed
    step.started_at = 111.0
    step.completed_at = 222.0
    step.duration_ms = 111.0
    normalize_for_resume(run)
    assert step.status == StepStatus.pending
    assert step.started_at is None and step.completed_at is None and step.duration_ms is None


def test_reset_step_helper_clears_stale_timing():
    step = StepState(id="x", story_id="s1", status=StepStatus.done,
                      started_at=1.0, completed_at=2.0, duration_ms=1.0)
    orchestrator._reset_step(step)
    assert step.status == StepStatus.pending
    assert step.started_at is None and step.completed_at is None and step.duration_ms is None


def test_restart_run_clears_stale_timing(monkeypatch):
    async def scenario():
        run = _build("run_test_restart_timing", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.done
        step.started_at = 10.0
        step.completed_at = 20.0
        step.duration_ms = 10.0

        async def _fake_loop(run_, client, listener):
            return None
        monkeypatch.setattr(orchestrator, "_run_loop", _fake_loop)

        result = await orchestrator.restart_run(run.run_id, None, None)
        assert result["status"] == "restarted"
        assert step.status == StepStatus.pending
        assert step.started_at is None and step.completed_at is None and step.duration_ms is None
        task = orchestrator._active_tasks.pop(run.run_id, None)
        if task:
            await task
    run_async(scenario())


def test_jump_to_step_clears_stale_timing_on_target_and_dependents():
    async def scenario():
        run = _build("run_test_jump_timing", [
            StepInput(id="step_a", title="A", acceptance_criteria=["PROBE: true"]),
            StepInput(id="step_b", title="B", depends_on=["step_a"], acceptance_criteria=["PROBE: true"]),
        ])
        step_a, step_b = run.epics[0].stories[0].steps
        for s in (step_a, step_b):
            s.status = StepStatus.done
            s.started_at = 1000.0
            s.completed_at = 2000.0
            s.duration_ms = 1000.0
        run.status = RunStatus.paused
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        try:
            result = await orchestrator.jump_to_step(run.run_id, "step_a", None, True)
            assert result["status"] == "jump_scheduled"
            assert step_a.status == StepStatus.ready
            assert step_a.started_at is None and step_a.completed_at is None and step_a.duration_ms is None
            assert step_b.status == StepStatus.pending  # dependent, reset too
            assert step_b.started_at is None and step_b.completed_at is None and step_b.duration_ms is None
        finally:
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_park_for_decision_does_not_overwrite_the_last_attempts_timing(monkeypatch):
    """P5: decision_pending is NOT terminal — _park_for_decision must leave
    started_at/completed_at/duration_ms EXACTLY as the last concluded attempt
    left them (never re-stamp 'now' — that made a merely-parked step look
    freshly finished)."""
    async def scenario():
        run = _build("run_test_park_timing", [
            StepInput(id="step_x", title="X", max_attempts=1, acceptance_criteria=["PROBE: true"]),
        ])
        step = run.epics[0].stories[0].steps[0]

        async def fake_exec(run_, epic, story, step_, client, listener):
            # Mirrors the REAL _execute_single_step failure path: it stamps
            # started_at/completed_at/duration_ms itself when the attempt ends.
            step_.status = StepStatus.failed
            step_.started_at = 1_000.0
            step_.completed_at = 1_345.0
            step_.duration_ms = 345.0

        monkeypatch.setattr(orchestrator, "_execute_single_step", fake_exec)
        epic, story = run.epics[0], run.epics[0].stories[0]
        task = asyncio.create_task(orchestrator._execute_story_steps(run, epic, story, None, None))
        orchestrator._active_tasks[run.run_id] = task
        try:
            assert await _wait_for(lambda: step.status == StepStatus.decision_pending)
            assert step.started_at == 1_000.0
            assert step.completed_at == 1_345.0  # NOT re-stamped to "now"
            assert step.duration_ms == 345.0
        finally:
            if not task.done():
                task.cancel()
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_review_step_parks_decision_pending_with_no_timing_at_all():
    """A review step is NEVER sent to _execute_single_step. Parking it for a
    decision must not fabricate a completed_at/started_at it never earned."""
    async def scenario():
        run = _build("run_test_review_timing", [
            StepInput(id="step_review", title="Review", review=True),
        ])
        step = run.epics[0].stories[0].steps[0]
        epic, story = run.epics[0], run.epics[0].stories[0]
        task = asyncio.create_task(orchestrator._execute_story_steps(run, epic, story, None, None))
        orchestrator._active_tasks[run.run_id] = task
        try:
            assert await _wait_for(lambda: step.status == StepStatus.decision_pending)
            assert step.started_at is None
            assert step.completed_at is None
            assert step.duration_ms is None
        finally:
            if not task.done():
                task.cancel()
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


# ── (3) phantom 'running' runs → 'interrupted' at boot ────────────────────


def _seed_run_row(conn_execute, run_id: str, status: str, state_json: str, ts: float):
    return conn_execute(
        """INSERT INTO runs (run_id, goal, repo_dir, model, status, project, state_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (run_id, "g", "/tmp", "m", status, "demo", state_json, ts, ts),
    )


def test_boot_marks_phantom_running_as_interrupted_with_trace_and_event(tmp_path):
    async def scenario():
        conn = await aiosqlite.connect(tmp_path / "phantom.db")
        conn.row_factory = aiosqlite.Row
        try:
            await persistence.init_tables(conn)  # fresh schema; both passes no-op
            now = time.time() * 1000
            phantom_blob = json.dumps({
                "run_id": "run_phantom", "goal": "g", "repo_dir": "/tmp", "model": "m",
                "status": "running", "project": "demo", "created_at": now, "updated_at": now,
                "epics": [], "trace": [{"seq": 1, "timestamp": now, "type": "run_started",
                                        "step_id": None, "story_id": None, "epic_id": None, "payload": {}}],
            })
            paused_blob = json.dumps({
                "run_id": "run_paused_ok", "goal": "g", "repo_dir": "/tmp", "model": "m",
                "status": "paused", "project": "demo", "created_at": now, "updated_at": now,
                "epics": [], "trace": [],
            })
            await _seed_run_row(conn.execute, "run_phantom", "running", phantom_blob, now)
            await _seed_run_row(conn.execute, "run_paused_ok", "paused", paused_blob, now)
            await _seed_run_row(conn.execute, "run_corrupt_running", "running", "{not json", now)
            await conn.commit()

            await persistence.init_tables(conn)  # the boot pass runs now

            cur = await conn.execute("SELECT run_id, status, state_json FROM runs")
            rows = {r["run_id"]: r for r in await cur.fetchall()}

            assert rows["run_phantom"]["status"] == "interrupted"
            fixed = json.loads(rows["run_phantom"]["state_json"])
            assert fixed["status"] == "interrupted"
            notes = [t for t in fixed["trace"] if t.get("type") == "run_interrupted"]
            assert len(notes) == 1
            assert "no live process" in notes[0]["payload"]["note"]
            assert any(t.get("type") == "run_started" for t in fixed["trace"])  # original kept

            assert rows["run_paused_ok"]["status"] == "paused"  # untouched
            assert json.loads(rows["run_paused_ok"]["state_json"]) == json.loads(paused_blob)

            # corrupt blob: column still fixed, blob left alone (never blocks boot)
            assert rows["run_corrupt_running"]["status"] == "interrupted"
            assert rows["run_corrupt_running"]["state_json"] == "{not json"

            ev_cur = await conn.execute(
                "SELECT run_id FROM events WHERE type = 'run_interrupted' ORDER BY run_id")
            assert [r["run_id"] for r in await ev_cur.fetchall()] == ["run_corrupt_running", "run_phantom"]

            # idempotent: a further boot pass must not duplicate the note/event
            await persistence.init_tables(conn)
            cur2 = await conn.execute("SELECT state_json FROM runs WHERE run_id = 'run_phantom'")
            again = json.loads((await cur2.fetchone())["state_json"])
            assert len([t for t in again["trace"] if t.get("type") == "run_interrupted"]) == 1
            ev_cur2 = await conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE run_id = 'run_phantom' AND type = 'run_interrupted'")
            assert (await ev_cur2.fetchone())["n"] == 1
        finally:
            await conn.close()
    asyncio.run(scenario())


def test_try_resume_run_accepts_interrupted_status(monkeypatch):
    """Functional regression guard: before this fix, a phantom 'running' row was
    load_run-normalized to 'paused' (resumable). After introducing 'interrupted'
    as its own status, try_resume_run must explicitly accept it too, or a boot-
    fixed run could never be resumed via POST /runs/{id}/resume again."""
    async def scenario():
        run = _build("run_test_resume_interrupted", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
        ])
        run.status = RunStatus.interrupted

        async def _fake_loop(run_, client, listener):
            return None
        monkeypatch.setattr(orchestrator, "_run_loop", _fake_loop)

        ok = await orchestrator.try_resume_run(run.run_id, None, None)
        assert ok is True
        assert run.status == RunStatus.running
        task = orchestrator._active_tasks.pop(run.run_id, None)
        if task:
            await task
    run_async(scenario())


def test_interrupted_status_round_trips_through_persistence(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(settings, "db_path", str(tmp_path / "interrupted_rt.db"))
        run = _build("run_test_interrupted_roundtrip", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
        ])
        run.status = RunStatus.interrupted
        await persistence.save_run(run)
        loaded = await persistence.load_run(run.run_id)
        assert loaded.status == RunStatus.interrupted  # NOT normalized like 'running' is
    run_async(scenario())


# ── (4) audit JSONL: persistent default + legacy fallback ────────────────


def test_default_audit_dir_is_persistent_and_package_anchored(monkeypatch):
    # conftest.py sets ORCHESTRATOR_AUDIT_DIR for the whole test session (so the
    # suite itself never writes into the real repo) — override it back to None
    # here to exercise the actual "no override" fallback this test targets.
    monkeypatch.setattr(settings, "audit_dir", None)
    d = audit_mod.default_audit_dir()
    assert d.is_absolute()
    assert d == audit_mod.DEFAULT_AUDIT_DIR
    assert str(d).endswith("migration-orchestrator/logs/audit")


def test_default_audit_dir_respects_settings_override(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "audit_dir", str(tmp_path / "custom-audit"))
    assert audit_mod.default_audit_dir() == tmp_path / "custom-audit"


def test_run_audit_logger_default_writes_under_persistent_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "audit_dir", str(tmp_path))
    logger = audit_mod.RunAuditLogger("run_persist_check")
    assert logger.log_dir == tmp_path
    logger.run_started("g", "m", 1)
    assert (tmp_path / "run_persist_check.jsonl").is_file()


def test_run_audit_logger_explicit_log_dir_still_overrides(tmp_path, monkeypatch):
    # explicit log_dir (as every existing test already passes) must still win
    # over both settings.audit_dir and the persistent default.
    monkeypatch.setattr(settings, "audit_dir", str(tmp_path / "not-this-one"))
    other = tmp_path / "explicit"
    logger = audit_mod.RunAuditLogger("run_explicit", log_dir=other)
    assert logger.log_dir == other


def test_audit_log_path_prefers_current_then_falls_back_to_legacy(tmp_path, monkeypatch):
    current_dir = tmp_path / "current"
    legacy_dir = tmp_path / "legacy"
    current_dir.mkdir()
    legacy_dir.mkdir()
    monkeypatch.setattr(audit_mod, "DEFAULT_AUDIT_DIR", current_dir)
    monkeypatch.setattr(settings, "audit_dir", None)
    monkeypatch.setattr(audit_mod, "LEGACY_AUDIT_DIR", legacy_dir)

    # neither exists yet → current path returned (caller checks .is_file())
    assert audit_mod.audit_log_path("run_p") == current_dir / "run_p.jsonl"

    # only the legacy file exists → falls back so old runs stay readable
    (legacy_dir / "run_p.jsonl").write_text("{}\n")
    assert audit_mod.audit_log_path("run_p") == legacy_dir / "run_p.jsonl"

    # current appears later (e.g. re-run under the new default) → current wins
    (current_dir / "run_p.jsonl").write_text("{}\n")
    assert audit_mod.audit_log_path("run_p") == current_dir / "run_p.jsonl"


def test_stats_route_reads_audit_log_via_audit_log_path(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_mod, "DEFAULT_AUDIT_DIR", tmp_path)
    monkeypatch.setattr(settings, "audit_dir", None)
    (tmp_path / "run_stats_test.jsonl").write_text(
        json.dumps({"event": "step_started", "step_id": "step_a"}) + "\n")

    async def scenario():
        result = await stats_routes.get_run_audit("run_stats_test")
        assert len(result) == 1 and result[0]["event"] == "step_started"
        assert await stats_routes.get_run_audit("run_never_ran") == []
    asyncio.run(scenario())


# ── (5) GET /runs/{run_id}/steps/{step_id}/log ────────────────────────────


def test_read_step_audit_entries_filters_sorts_and_survives_bad_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_mod, "DEFAULT_AUDIT_DIR", tmp_path)
    monkeypatch.setattr(settings, "audit_dir", None)
    (tmp_path / "run_log_test.jsonl").write_text("\n".join([
        json.dumps({"event": "probe_executed", "step_id": "step_a", "command": "c1", "exit_code": 0,
                    "passed": True, "stdout": "out1", "stderr": "", "duration_ms": 5.0, "ts": 200}),
        "not json at all",
        json.dumps({"event": "step_started", "step_id": "step_a"}),           # wrong event type
        json.dumps({"event": "command_executed", "step_id": "step_b", "command": "other"}),  # wrong step
        json.dumps({"event": "command_executed", "step_id": "step_a", "command": "c0", "exit_code": 1,
                    "passed": False, "stdout": "", "stderr": "boom", "duration_ms": 1.0, "ts": 100}),
    ]) + "\n")
    entries = audit_mod.read_step_audit_entries("run_log_test", "step_a")
    assert [e["command"] for e in entries] == ["c0", "c1"]  # oldest (ts) first
    assert entries[0]["kind"] == "command" and entries[0]["passed"] is False and entries[0]["stderr"] == "boom"
    assert entries[1]["kind"] == "probe" and entries[1]["stdout"] == "out1"


def test_read_step_audit_entries_missing_file_is_empty_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_mod, "DEFAULT_AUDIT_DIR", tmp_path / "nowhere")
    monkeypatch.setattr(settings, "audit_dir", None)
    assert audit_mod.read_step_audit_entries("run_ghost", "step_x") == []


def test_step_log_route_returns_captured_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_mod, "DEFAULT_AUDIT_DIR", tmp_path)
    monkeypatch.setattr(settings, "audit_dir", None)
    (tmp_path / "run_steplog.jsonl").write_text(
        json.dumps({"event": "command_executed", "step_id": "step_x", "command": "echo a",
                    "exit_code": 0, "passed": True, "stdout": "a", "stderr": "", "duration_ms": 2.0, "ts": 10}) + "\n")
    run = SimpleNamespace(run_id="run_steplog")
    monkeypatch.setattr(runs_routes, "get_run", lambda rid: run if rid == "run_steplog" else None)

    resp = _runs_client().get("/runs/run_steplog/steps/step_x/log")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"run_id": "run_steplog", "step_id": "step_x", "count": 1, "entries": [
        {"kind": "command", "command": "echo a", "exit_code": 0, "passed": True,
         "stdout": "a", "stderr": "", "duration_ms": 2.0, "ts": 10},
    ]}


def test_step_log_route_empty_entries_for_unknown_step(monkeypatch):
    run = SimpleNamespace(run_id="run_steplog2")
    monkeypatch.setattr(runs_routes, "get_run", lambda rid: run if rid == "run_steplog2" else None)
    resp = _runs_client().get("/runs/run_steplog2/steps/step_ghost/log")
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "run_steplog2", "step_id": "step_ghost", "entries": [], "count": 0}


def test_step_log_route_404_for_unknown_run(monkeypatch):
    monkeypatch.setattr(runs_routes, "get_run", lambda rid: None)

    async def _no_load(rid):
        return None
    monkeypatch.setattr(runs_routes, "load_run", _no_load)
    resp = _runs_client().get("/runs/ghost/steps/step_x/log")
    assert resp.status_code == 404


def test_decision_bundle_probes_and_commands_survive_the_audit_refactor(tmp_path, monkeypatch):
    """decision_bundles used to parse the audit JSONL inline; it now shares
    audit.read_step_audit_entries with the new per-step log endpoint. The
    bundle's probes/commands shape (stdout_tail/stderr_tail, 800c) must be
    unchanged."""
    monkeypatch.setattr(audit_mod, "DEFAULT_AUDIT_DIR", tmp_path)
    monkeypatch.setattr(settings, "audit_dir", None)
    run = _build("run_test_bundle_audit_refactor", [
        StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
    ])
    step = run.epics[0].stories[0].steps[0]
    step.status = StepStatus.decision_pending
    (tmp_path / f"{run.run_id}.jsonl").write_text("\n".join([
        json.dumps({"event": "probe_executed", "step_id": "step_x", "command": "pytest -q",
                    "exit_code": 1, "passed": False, "stdout": "x" * 10, "stderr": "y" * 10,
                    "duration_ms": 3.0, "ts": 1}),
        json.dumps({"event": "command_executed", "step_id": "step_x", "command": "echo hi",
                    "exit_code": 0, "passed": True, "stdout": "hi", "stderr": "", "duration_ms": 1.0, "ts": 2}),
        json.dumps({"event": "probe_executed", "step_id": "step_other", "command": "ignored"}),
    ]) + "\n")
    bundles = orchestrator.decision_bundles(run)
    assert len(bundles) == 1
    b = bundles[0]
    assert b["probes"] == [{"command": "pytest -q", "exit_code": 1, "passed": False,
                            "stdout_tail": "x" * 10, "stderr_tail": "y" * 10, "ts": 1}]
    assert b["commands"] == [{"command": "echo hi", "exit_code": 0, "passed": True,
                              "stdout_tail": "hi", "stderr_tail": "", "ts": 2}]


# ── (6) frontend StepStatus union carries decision_pending ────────────────


def test_frontend_step_status_union_includes_decision_pending():
    """Audit finding: the wire sends step.status == 'decision_pending' (see
    orchestrator._park_for_decision / StepStatus.decision_pending) and
    RunDetail.tsx already keys a color on it, but the StepStatus union in
    types.ts omitted it. Structural check (no TS toolchain in this suite) that
    the literal is present exactly once, comma-separated, in the union line."""
    types_ts = __import__("pathlib").Path(__file__).resolve().parents[1] / "frontend" / "src" / "types.ts"
    first_line = types_ts.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("export type StepStatus =")
    members = [m.strip().strip("'") for m in first_line.split("=", 1)[1].split("|")]
    assert members.count("decision_pending") == 1
    # every pre-existing member must still be present — additive only
    for m in ("pending", "ready", "running", "verifying", "done", "failed",
              "blocked", "waiting_human", "halted", "rejected"):
        assert m in members
