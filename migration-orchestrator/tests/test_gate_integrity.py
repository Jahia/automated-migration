"""P0.3 gate-integrity regression suite (QUALITY-PLAN §5).

Drives the state machine and orchestrator functions directly — no live engine,
no opencode, no HTTP. Async scenarios run under asyncio.run (sync tests) so the
suite needs no pytest-asyncio.
"""
from __future__ import annotations

import asyncio

import pytest

from src import orchestrator, persistence
from src.migration_control import compact_status
from src.models import (
    EpicInput,
    EpicStatus,
    PlanInput,
    RunStatus,
    StepInput,
    StepState,
    StepStatus,
    StoryInput,
    StoryStatus,
)
from src.state import (
    PlanLintError,
    build_run_state,
    gate_blocked_step,
    normalize_for_resume,
    select_next_ready_story,
)
from src.verifier import probe_commands


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


def _run_with_halted_gate(run_id: str):
    plan = _plan([
        StepInput(id="step_a", title="A", acceptance_criteria=["PROBE: true"]),
        StepInput(id="step_gate", title="Fidelity gate", depends_on=["step_a"],
                  acceptance_criteria=["PROBE: true"]),
        StepInput(id="step_b", title="B", depends_on=["step_gate"],
                  acceptance_criteria=["PROBE: true"]),
    ])
    run = build_run_state(plan)
    run.run_id = run_id
    steps = run.epics[0].stories[0].steps
    steps[0].status = StepStatus.done
    steps[1].status = StepStatus.halted
    run.status = RunStatus.paused
    orchestrator.register_run(run)
    return run, steps[1]


# ── (a) reject-then-resume does NOT mark the step done ────────────────


def test_reject_then_resume_does_not_mark_done():
    async def scenario():
        run, gate = _run_with_halted_gate("run_test_reject_resume")
        result = await orchestrator.reject_gate(run.run_id, "coverage too low")
        assert result["status"] == "rejected"
        assert result["step_id"] == gate.id
        assert gate.status == StepStatus.rejected

        ok = await orchestrator.try_resume_run(run.run_id, None, None)
        assert ok is False
        assert gate.status == StepStatus.rejected
        assert gate.status != StepStatus.done
        assert run.status == RunStatus.paused
    run_async(scenario())


def test_rejected_state_survives_persistence_roundtrip():
    async def scenario():
        run, gate = _run_with_halted_gate("run_test_reject_persist")
        await orchestrator.reject_gate(run.run_id, "bad model")
        loaded = await persistence.load_run(run.run_id)
        step = loaded.epics[0].stories[0].steps[1]
        assert step.status == StepStatus.rejected
    run_async(scenario())


# ── (b) resume leaves a halted step halted (no silent approval) ───────


def test_resume_leaves_halted_step_halted():
    async def scenario():
        run, gate = _run_with_halted_gate("run_test_resume_halted")
        ok = await orchestrator.try_resume_run(run.run_id, None, None)
        assert ok is False
        assert gate.status == StepStatus.halted
        assert run.status == RunStatus.paused

        ok = await orchestrator.resume_run(run.run_id)
        assert ok is False
        assert gate.status == StepStatus.halted
        assert run.status == RunStatus.paused
    run_async(scenario())


def test_normalize_for_resume_never_touches_gates():
    run, gate = _run_with_halted_gate("run_test_normalize")
    steps = run.epics[0].stories[0].steps
    steps[2].status = StepStatus.failed
    normalize_for_resume(run)
    assert gate.status == StepStatus.halted
    assert steps[2].status == StepStatus.pending
    gate.status = StepStatus.rejected
    normalize_for_resume(run)
    assert gate.status == StepStatus.rejected
    assert gate_blocked_step(run) is gate


# ── (c) approve endpoint logic marks the halted step done ─────────────


def test_approve_gate_marks_step_done():
    async def scenario():
        run, gate = _run_with_halted_gate("run_test_approve")
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        try:
            result = await orchestrator.approve_gate(run.run_id, None, None)
            assert result["status"] == "approved"
            assert result["step_id"] == gate.id
            assert gate.status == StepStatus.done
            assert run.status == RunStatus.running
        finally:
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_approve_gate_without_halted_step_errors():
    async def scenario():
        plan = _plan([StepInput(id="step_a", title="A", acceptance_criteria=["PROBE: true"])])
        run = build_run_state(plan)
        run.run_id = "run_test_approve_nogate"
        run.status = RunStatus.paused
        orchestrator.register_run(run)
        result = await orchestrator.approve_gate(run.run_id, None, None)
        assert result.get("error") == "no halted gate step"
    run_async(scenario())


# ── (c2) engine-restart recovery: running story/epic become selectable ─
# A run persisted mid-story records story=running, epic=running. After an
# engine restart there is no in-flight loop, and select_next_ready_story only
# picks pending — without normalization, approve_gate spawns a fresh loop that
# instantly fails the epic and the run.


def test_normalize_resets_running_story_and_epic_after_restart():
    run, gate = _run_with_halted_gate("run_test_normalize_running")
    epic = run.epics[0]
    story = epic.stories[0]
    epic.status = EpicStatus.running
    story.status = StoryStatus.running
    gate.status = StepStatus.done  # gate was just approved
    normalize_for_resume(run)
    assert story.status == StoryStatus.pending
    assert epic.status == EpicStatus.pending
    assert select_next_ready_story(epic) is story


def test_approve_gate_after_engine_restart_spawns_runnable_loop(monkeypatch):
    async def scenario():
        run, gate = _run_with_halted_gate("run_test_approve_restart")
        epic = run.epics[0]
        story = epic.stories[0]
        epic.status = EpicStatus.running
        story.status = StoryStatus.running  # persisted at halt; no active task
        spawned = []

        async def fake_loop(run_, client, listener):
            spawned.append(run_)

        monkeypatch.setattr(orchestrator, "_run_loop", fake_loop)
        try:
            result = await orchestrator.approve_gate(run.run_id, None, None)
            assert result["status"] == "approved"
            assert gate.status == StepStatus.done
            assert run.status == RunStatus.running
            # the fresh loop got spawned AND can actually pick up the story
            assert spawned == [run]
            assert story.status == StoryStatus.pending
            assert select_next_ready_story(epic) is story
        finally:
            task = orchestrator._active_tasks.pop(run.run_id, None)
            if task:
                await task
    run_async(scenario())


# ── (c3) jump with no active loop spawns a fresh loop (no zombie run) ──


def test_jump_with_no_active_loop_spawns_fresh_loop(monkeypatch):
    async def scenario():
        run, gate = _run_with_halted_gate("run_test_jump_restart")
        epic = run.epics[0]
        story = epic.stories[0]
        epic.status = EpicStatus.running
        story.status = StoryStatus.running
        gate.status = StepStatus.rejected  # jump is the documented redo path
        spawned = []

        async def fake_loop(run_, client, listener):
            spawned.append(run_)

        monkeypatch.setattr(orchestrator, "_run_loop", fake_loop)
        try:
            result = await orchestrator.jump_to_step(run.run_id, gate.id)
            assert result["status"] == "jump_scheduled"
            assert run.status == RunStatus.running
            assert run.forced_next_step == gate.id
            assert spawned == [run]
            # the rejected gate was reset, so nothing blocks the fresh loop
            assert gate_blocked_step(run) is None
            assert story.status == StoryStatus.pending
        finally:
            task = orchestrator._active_tasks.pop(run.run_id, None)
            if task:
                await task
    run_async(scenario())


# ── (c4) compact_status surfaces a rejected gate (no dead end) ─────────


def test_compact_status_surfaces_rejected_gate():
    run, gate = _run_with_halted_gate("run_test_compact_rejected")
    gate.status = StepStatus.rejected
    gate.gate_type = "fidelity"
    status = compact_status(run, None)
    assert status["gate"] is not None
    assert status["gate"]["step_id"] == gate.id
    assert status["gate"]["status"] == "rejected"
    assert status["next_actions"] == ["rollback", "jump", "restart"]


# ── (d) plan lint: deploy/content/publish/scaffold need a PROBE ───────


def test_plan_lint_rejects_probeless_deploy_step():
    plan = _plan([
        StepInput(id="step_deploy", title="Deploy the module",
                  acceptance_criteria=["Run: yarn build && yarn jahia-deploy"]),
    ])
    with pytest.raises(PlanLintError) as exc:
        build_run_state(plan)
    assert "step_deploy" in str(exc.value)


def test_plan_lint_accepts_deploy_step_with_probe():
    plan = _plan([
        StepInput(id="step_deploy", title="Deploy the module",
                  acceptance_criteria=["PROBE: test -f module.tgz"]),
    ])
    run = build_run_state(plan)
    assert run.epics[0].stories[0].steps[0].id == "step_deploy"


def test_plan_lint_counts_probe_with_timeout_override():
    plan = _plan([
        StepInput(id="step_publish_site", title="Publish everything",
                  acceptance_criteria=["PROBE[900]: bash orchestration/probes/publish-parity.sh"]),
    ])
    build_run_state(plan)


def test_plan_lint_matches_title_not_only_id():
    plan = _plan([
        StepInput(id="step_x", title="Content load via MCP", acceptance_criteria=[]),
    ])
    with pytest.raises(PlanLintError):
        build_run_state(plan)


# ── (e) PROBE[NNN] timeout override + env default ─────────────────────


def test_probe_timeout_override_and_default(monkeypatch):
    monkeypatch.delenv("ORCHESTRATOR_PROBE_TIMEOUT", raising=False)
    step = StepState(id="s", story_id="st", acceptance_criteria=[
        "PROBE[900]: yarn build && yarn jahia-deploy",
        "PROBE: echo hi",
        "not a probe",
    ])
    assert probe_commands(step) == [
        ("yarn build && yarn jahia-deploy", 900.0),
        ("echo hi", 600.0),
    ]


def test_probe_timeout_default_from_env(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_PROBE_TIMEOUT", "1200")
    step = StepState(id="s", story_id="st", acceptance_criteria=[
        "PROBE[900]: sleep 1",
        "PROBE: echo hi",
    ])
    assert probe_commands(step) == [("sleep 1", 900.0), ("echo hi", 1200.0)]
