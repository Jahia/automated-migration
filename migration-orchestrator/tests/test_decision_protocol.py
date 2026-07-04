"""Decision-protocol suite (ASSIST-PLAN §3 Phase A).

Covers: plan lint (strategy PROBE preservation + review exemption), the
decision_pending transition (retries exhausted WITH or WITHOUT strategies /
review steps — P5.5b: retries exhausted ALWAYS parks, never fails), the decide
endpoint semantics (strategy apply+rerun, proceed, halt, refusals, autonomy
gating of free-form patches, and the P5.5b retry/repatch actions — U4 inputs-only
+ PROBE lint), deterministic epic approval (the LLM reviewer is gone),
scope-rules file writing, resume refusal, compact_status projection, the
retry-on-verification-failure fix (P4 regression: step_segment died at attempt
1/3 because the retry branch set 'ready', which select_next_ready_step never
picks), the human-answer re-execution fix, and the C3 absolute cost dir.

Same style as test_gate_integrity.py: drives the state machine and
orchestrator functions directly — no live engine, no opencode, no HTTP.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from src import cost_tracker, orchestrator, persistence
from src.migration_control import compact_status
from src.models import (
    EpicInput,
    PlanInput,
    RunStatus,
    StepInput,
    StepStatus,
    StoryInput,
    Strategy,
    StrategyPatch,
)
from src.prompt_builder import build_step_prompt
from src.state import PlanLintError, build_run_state, gate_blocked_step, normalize_for_resume


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


def _build(run_id: str, steps: list[StepInput], autonomy: str = "assisted"):
    run = build_run_state(_plan(steps))
    run.run_id = run_id
    run.autonomy = autonomy
    orchestrator.register_run(run)
    return run


async def _wait_for(predicate, timeout: float = 5.0):
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


# ── (1) plan lint: strategy PROBE preservation + review exemption ──────


def _segment_step(strategies: list[Strategy]) -> StepInput:
    return StepInput(id="step_segment", title="Vision segmentation",
                     acceptance_criteria=["Run: node segment_probe.mjs projects/p",
                                          "PROBE: ls projects/p/workflow-output/segment/*.json"],
                     strategies=strategies)


def test_lint_rejects_strategy_patch_dropping_probe_line():
    strat = Strategy(id="s1", patches=[StrategyPatch(
        step_id="step_segment",
        acceptance_criteria=["Run: node segment_probe.mjs projects/p --consensus 3"])])
    with pytest.raises(PlanLintError) as exc:
        build_run_state(_plan([_segment_step([strat])]))
    assert "PROBE" in str(exc.value)
    assert "s1" in str(exc.value)


def test_lint_accepts_strategy_patch_preserving_probes_with_additions():
    strat = Strategy(id="s1", patches=[StrategyPatch(
        step_id="step_segment",
        acceptance_criteria=["Run: node segment_probe.mjs projects/p --consensus 3",
                             "PROBE: ls projects/p/workflow-output/segment/*.json",
                             "PROBE: test -s projects/p/workflow-output/segment/segment-check.json"])])
    run = build_run_state(_plan([_segment_step([strat])]))
    assert run.epics[0].stories[0].steps[0].strategies[0].id == "s1"


def test_lint_exempts_arm_swap_strategy():
    strat = Strategy(id="heuristic_arm", arm_swap=True, patches=[StrategyPatch(
        step_id="step_segment",
        acceptance_criteria=["Run: python3 group_llm.py projects/p",
                             "PROBE: test -s projects/p/workflow-output/grouping.json"])])
    build_run_state(_plan([_segment_step([strat])]))


def test_lint_inputs_only_patch_is_fine():
    strat = Strategy(id="sample3", patches=[StrategyPatch(step_id="step_segment", inputs={"per_cluster": 3})])
    build_run_state(_plan([_segment_step([strat])]))


def test_lint_rejects_patch_targeting_unknown_step():
    strat = Strategy(id="s1", patches=[StrategyPatch(step_id="step_ghost", inputs={})])
    with pytest.raises(PlanLintError) as exc:
        build_run_state(_plan([_segment_step([strat])]))
    assert "step_ghost" in str(exc.value)


def test_lint_exempts_review_steps_from_probe_requirement():
    # 'model review' would normally trip the deploy/content/publish/scaffold…
    # no — it trips nothing; use a title that matches the gated regex:
    plan = _plan([StepInput(id="step_model_review", title="Content model review",
                            review=True, acceptance_criteria=[])])
    run = build_run_state(plan)
    assert run.epics[0].stories[0].steps[0].review is True


def test_lint_still_rejects_probeless_deploy_step():
    with pytest.raises(PlanLintError):
        build_run_state(_plan([StepInput(id="step_deploy", title="Deploy", acceptance_criteria=[])]))


# ── (2) retry semantics: verification failure RETRIES up to max_attempts ──
# P4 regression (run_1783106607306): the old retry branch set the failed step
# to 'ready', which select_next_ready_step never picks (pending only) — the
# step silently got ZERO retries and the story failed with the step parked at
# attempt 1. The fix re-queues it as 'pending'.


def test_verification_failure_retries_up_to_max_attempts(monkeypatch):
    async def scenario():
        run = _build("run_test_retry_fix", [
            StepInput(id="step_x", title="X", max_attempts=3, acceptance_criteria=["PROBE: true"]),
        ])
        step = run.epics[0].stories[0].steps[0]
        attempts_seen: list[int] = []

        async def fake_exec(run_, epic, story, step, client, listener):
            attempts_seen.append(step.attempt)
            step.status = StepStatus.failed

        monkeypatch.setattr(orchestrator, "_execute_single_step", fake_exec)
        epic, story = run.epics[0], run.epics[0].stories[0]
        # P5.5b: after the budgeted retries, an exhausted step PARKS for a decision
        # (never a silent return), so drive the loop with a task and wait for it.
        task = asyncio.create_task(orchestrator._execute_story_steps(run, epic, story, None, None))
        orchestrator._active_tasks[run.run_id] = task
        try:
            assert await _wait_for(lambda: step.status == StepStatus.decision_pending)
            # attempt is a 1-based execution counter; max_attempts = total budget
            assert attempts_seen == [1, 2, 3]
            assert step.attempt == 3
        finally:
            if not task.done():
                task.cancel()
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_failure_then_success_on_retry(monkeypatch):
    async def scenario():
        run = _build("run_test_retry_ok", [
            StepInput(id="step_x", title="X", max_attempts=3, acceptance_criteria=["PROBE: true"]),
        ])
        calls = {"n": 0}

        async def fake_exec(run_, epic, story, step, client, listener):
            calls["n"] += 1
            step.status = StepStatus.failed if calls["n"] == 1 else StepStatus.done

        monkeypatch.setattr(orchestrator, "_execute_single_step", fake_exec)
        epic, story = run.epics[0], run.epics[0].stories[0]
        await orchestrator._execute_story_steps(run, epic, story, None, None)
        assert calls["n"] == 2
        assert story.steps[0].status == StepStatus.done
    run_async(scenario())


# ── (3) decision_pending on retries-exhausted-with-strategies ──────────


def test_retries_exhausted_with_strategies_goes_decision_pending(monkeypatch):
    async def scenario():
        strat = Strategy(id="consensus3", title="Upfront N=3 consensus", order=1, patches=[
            StrategyPatch(step_id="step_x", inputs={"consensus": 3},
                          acceptance_criteria=["PROBE: true", "extra criterion"]),
        ])
        run = _build("run_test_decision_transition", [
            StepInput(id="step_x", title="X", max_attempts=2,
                      acceptance_criteria=["PROBE: true"], strategies=[strat]),
        ])
        calls = {"n": 0}

        async def fake_exec(run_, epic, story, step, client, listener):
            calls["n"] += 1
            step.status = StepStatus.failed if calls["n"] <= 2 else StepStatus.done

        monkeypatch.setattr(orchestrator, "_execute_single_step", fake_exec)
        epic, story = run.epics[0], run.epics[0].stories[0]
        step = story.steps[0]
        task = asyncio.create_task(orchestrator._execute_story_steps(run, epic, story, None, None))
        orchestrator._active_tasks[run.run_id] = task
        try:
            assert await _wait_for(lambda: step.status == StepStatus.decision_pending)
            assert calls["n"] == 2  # both budgeted attempts ran BEFORE the decision point
            assert run.status == RunStatus.paused

            # decision_pending blocks plain resume (like halted/rejected)
            assert gate_blocked_step(run) is step
            ok = await orchestrator.resume_run(run.run_id)
            assert ok is False
            assert step.status == StepStatus.decision_pending

            # compact_status projects the decision gate
            st = compact_status(run, None)
            assert st["gate"] == {"active": True, "type": "decision", "step_id": "step_x",
                                  "status": "decision_pending", "summary": st["gate"]["summary"]}
            assert "strategies remaining: consensus3" in st["gate"]["summary"]
            assert st["next_actions"] == ["decide", "rollback", "restart"]

            # normalize_for_resume leaves decision_pending untouched
            normalize_for_resume(run)
            assert step.status == StepStatus.decision_pending

            # decide: apply the strategy → patch applied, attempts reset, rerun
            res = await orchestrator.decide_step(
                run.run_id, "step_x", action="apply_and_rerun",
                strategy_id="consensus3", rationale="stability RED, widen the estimator")
            assert res["status"] == "applied"
            await asyncio.wait_for(task, 5)
            assert step.status == StepStatus.done
            assert step.inputs == {"consensus": 3}
            assert step.acceptance_criteria == ["PROBE: true", "extra criterion"]
            assert step.strategies_applied == ["consensus3"]
            assert calls["n"] == 3
            assert run.status == RunStatus.running
        finally:
            if not task.done():
                task.cancel()
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_retries_exhausted_without_strategies_goes_decision_pending(monkeypatch):
    """P5.5b (Julian's directive 3): retries exhausted → ALWAYS decision_pending,
    even with NO pre-registered strategies. The run PAUSES; DeepSeek is out of the
    loop, so there is no repair fallback — the operator decides (retry/repatch/
    rollback). A plain resume is refused while the decision is pending."""
    async def scenario():
        run = _build("run_test_no_strategies_decision", [
            StepInput(id="step_x", title="X", max_attempts=1, acceptance_criteria=["PROBE: true"]),
        ])
        step = run.epics[0].stories[0].steps[0]

        async def fake_exec(run_, epic, story, step, client, listener):
            step.status = StepStatus.failed
            step.failure_context = "Run: line failed\nExit code: 2\nstderr (queue):\nboom"

        monkeypatch.setattr(orchestrator, "_execute_single_step", fake_exec)
        epic, story = run.epics[0], run.epics[0].stories[0]
        task = asyncio.create_task(orchestrator._execute_story_steps(run, epic, story, None, None))
        orchestrator._active_tasks[run.run_id] = task
        try:
            assert await _wait_for(lambda: step.status == StepStatus.decision_pending)
            assert run.status == RunStatus.paused
            assert gate_blocked_step(run) is step  # blocks plain resume
            ok = await orchestrator.resume_run(run.run_id)
            assert ok is False
            assert step.status == StepStatus.decision_pending

            # bundle carries the exhausted-retries reason + the failing command context
            b = orchestrator.decision_bundles(run)[0]
            assert b["reason"] == "retries_exhausted"
            assert b["failure_context"] and "Exit code: 2" in b["failure_context"]
            # no strategies → next_actions is retry/repatch/rollback/restart (no strategy)
            assert b["next_actions"] == ["retry", "repatch", "rollback", "restart"]
        finally:
            if not task.done():
                task.cancel()
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


# ── (3b) P5.5b: retry resets attempts; repatch merges inputs only ──────


def test_decide_retry_resets_attempts_and_reruns(monkeypatch):
    """action=retry re-queues the step UNCHANGED with a fresh attempt budget and
    clears failure_context. It refuses any strategy_id/patch/rules (it is a pure
    re-run). The decision is audited."""
    async def scenario():
        run = _build("run_test_retry_action", [
            StepInput(id="step_x", title="X", max_attempts=1, acceptance_criteria=["PROBE: true"]),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        step.attempt = 1
        step.failure_context = "boom"
        run.status = RunStatus.paused
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        try:
            # retry does not take strategy/patch/rules
            res = await orchestrator.decide_step(run.run_id, "step_x", action="retry",
                                                 strategy_id="s1", rationale="r")
            assert res["code"] == 400 and "retry takes no" in res["error"]

            res = await orchestrator.decide_step(run.run_id, "step_x", action="retry",
                                                 rationale="jahia restarted out of band")
            assert res["status"] == "retried"
            assert step.status == StepStatus.ready  # reset by the jump machinery
            assert step.attempt == 0
            assert step.failure_context is None
            assert run.forced_next_step == "step_x"
        finally:
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_decide_repatch_merges_inputs_only(monkeypatch):
    """action=repatch merges `inputs` (keeping keys the operator didn't send),
    clears failure_context, resets attempts and re-runs. Allowed in any autonomy
    (it cannot move a bar)."""
    async def scenario():
        run = _build("run_test_repatch_action", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"],
                      inputs={"consensus": 2, "keep": "me"}),
        ], autonomy="assisted")
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        step.attempt = 3
        step.failure_context = "boom"
        run.status = RunStatus.paused
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        try:
            res = await orchestrator.decide_step(
                run.run_id, "step_x", action="repatch",
                repatch_inputs={"consensus": 5}, rationale="widen the estimator")
            assert res["status"] == "repatched"
            assert res["target_step_id"] == "step_x"
            # merge, not replace: 'keep' survives, 'consensus' updated
            assert step.inputs == {"consensus": 5, "keep": "me"}
            assert step.failure_context is None
            assert step.attempt == 0  # reset by the jump machinery
            assert step.status == StepStatus.ready
            assert run.forced_next_step == "step_x"
        finally:
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_decide_repatch_refuses_acceptance_criteria_and_probe(monkeypatch):
    """U4 / amendment 4b: repatch is inputs-ONLY. acceptance_criteria (and its
    PROBE: lines) are frozen bars — any field beyond `inputs` (surfaced via the
    route's extra-field tripwire) is refused with a rule-1 message, and a missing
    `inputs` object is refused too."""
    async def scenario():
        run = _build("run_test_repatch_lint", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"], inputs={"a": 1}),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused

        # a repatch smuggling acceptance_criteria (route surfaces it as repatch_extra)
        res = await orchestrator.decide_step(
            run.run_id, "step_x", action="repatch",
            repatch_inputs={"a": 2},
            repatch_extra={"acceptance_criteria": ["only prose"]},
            rationale="r")
        assert res["code"] == 400
        assert "acceptance_criteria" in res["error"] and "frozen bars" in res["error"]
        assert step.inputs == {"a": 1}  # nothing changed

        # a repatch with no inputs object is refused
        res = await orchestrator.decide_step(run.run_id, "step_x", action="repatch",
                                             repatch_inputs=None, rationale="r")
        assert res["code"] == 400 and "inputs" in res["error"]

        # repatch may not carry strategy_id/patch
        res = await orchestrator.decide_step(run.run_id, "step_x", action="repatch",
                                             repatch_inputs={"a": 2}, strategy_id="s1", rationale="r")
        assert res["code"] == 400 and "inputs` only" in res["error"]
    run_async(scenario())


def test_decide_retry_and_repatch_are_audited(tmp_path):
    """Both new actions write a 'decision' event to the JSONL audit trail (the
    audit source of truth). repatch records the inputs_before/after + keys_changed."""
    async def scenario():
        import src.audit as audit_mod
        run = _build("run_test_actions_audit", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"],
                      inputs={"consensus": 2}),
        ])
        # register a temp-dir logger for this run so decide_step's get_audit_logger
        # (a module dict) returns it and writes the JSONL under tmp_path.
        audit_mod._loggers[run.run_id] = audit_mod.RunAuditLogger(run.run_id, log_dir=tmp_path)
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        try:
            await orchestrator.decide_step(run.run_id, "step_x", action="repatch",
                                           repatch_inputs={"consensus": 5}, rationale="widen")
            step.status = StepStatus.decision_pending  # pretend it parked again
            await orchestrator.decide_step(run.run_id, "step_x", action="retry", rationale="again")
            lines = (tmp_path / f"{run.run_id}.jsonl").read_text().splitlines()
            entries = [json.loads(l) for l in lines if l.strip()]
            decisions = [e for e in entries if e.get("event") == "decision"]
            assert len(decisions) == 2
            repatch_ev = next(d for d in decisions if d.get("action") == "repatch")
            assert repatch_ev["repatch"]["inputs_after"] == {"consensus": 5}
            assert repatch_ev["repatch"]["keys_changed"] == ["consensus"]
            assert any(d.get("action") == "retry" for d in decisions)
        finally:
            audit_mod._loggers.pop(run.run_id, None)
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


# ── (3c) P5.5b: deterministic epic approval (the LLM reviewer is gone) ──


def _epic_of(run):
    return run.epics[0]


def test_epic_all_green_true_when_every_step_done_and_verified():
    run = _build("run_test_epic_green", [
        StepInput(id="step_a", title="A", acceptance_criteria=["PROBE: true"]),
        StepInput(id="step_b", title="B", acceptance_criteria=["PROBE: true"]),
    ])
    from src.models import VerificationResult
    for s in run.epics[0].stories[0].steps:
        s.status = StepStatus.done
        s.verification = VerificationResult(passed=True, checks=["ok"], errors=[])
    assert orchestrator._epic_all_green(_epic_of(run)) is True
    verdicts = orchestrator._epic_verdicts(_epic_of(run))
    assert [v["step_id"] for v in verdicts] == ["step_a", "step_b"]
    assert all(v["status"] == "done" and v["verification_passed"] for v in verdicts)


def test_epic_all_green_false_when_a_step_not_done():
    run = _build("run_test_epic_notdone", [
        StepInput(id="step_a", title="A", acceptance_criteria=["PROBE: true"]),
        StepInput(id="step_b", title="B", acceptance_criteria=["PROBE: true"]),
    ])
    steps = run.epics[0].stories[0].steps
    steps[0].status = StepStatus.done
    steps[1].status = StepStatus.pending  # not done
    assert orchestrator._epic_all_green(_epic_of(run)) is False


def test_epic_all_green_false_when_verification_failed():
    run = _build("run_test_epic_verifail", [
        StepInput(id="step_a", title="A", acceptance_criteria=["PROBE: true"]),
    ])
    from src.models import VerificationResult
    s = run.epics[0].stories[0].steps[0]
    s.status = StepStatus.done
    s.verification = VerificationResult(passed=False, checks=[], errors=["probe X failed"])
    assert orchestrator._epic_all_green(_epic_of(run)) is False
    v = orchestrator._epic_verdicts(_epic_of(run))[0]
    assert v["verification_passed"] is False and v["errors"] == ["probe X failed"]


# ── (4) review steps: decision_pending WITHOUT any agent execution ─────


def test_review_step_goes_decision_pending_and_proceed_completes(monkeypatch):
    async def scenario():
        run = _build("run_test_review_step", [
            StepInput(id="step_a", title="A", acceptance_criteria=["PROBE: true"]),
            StepInput(id="step_model_review", title="Model review", review=True,
                      depends_on=["step_a"]),
            StepInput(id="step_b", title="B", depends_on=["step_model_review"],
                      acceptance_criteria=["PROBE: true"]),
        ])
        executed: list[str] = []

        async def fake_exec(run_, epic, story, step, client, listener):
            executed.append(step.id)
            step.status = StepStatus.done

        monkeypatch.setattr(orchestrator, "_execute_single_step", fake_exec)
        epic, story = run.epics[0], run.epics[0].stories[0]
        review = story.steps[1]
        task = asyncio.create_task(orchestrator._execute_story_steps(run, epic, story, None, None))
        orchestrator._active_tasks[run.run_id] = task
        try:
            assert await _wait_for(lambda: review.status == StepStatus.decision_pending)
            assert run.status == RunStatus.paused
            assert executed == ["step_a"]  # the review step was NEVER sent to an agent

            res = await orchestrator.decide_step(
                run.run_id, "step_model_review", action="proceed",
                rationale="manifest editorially sound")
            assert res["status"] == "proceeded"
            await asyncio.wait_for(task, 5)
            assert review.status == StepStatus.done
            assert executed == ["step_a", "step_b"]  # review never executed
        finally:
            if not task.done():
                task.cancel()
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_proceed_refused_on_non_review_step():
    async def scenario():
        run = _build("run_test_proceed_refused", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"],
                      strategies=[Strategy(id="s1")]),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        res = await orchestrator.decide_step(run.run_id, "step_x", action="proceed", rationale="r")
        assert res["error"] and res["code"] == 400
        assert step.status == StepStatus.decision_pending
    run_async(scenario())


# ── (5) decide refusals ────────────────────────────────────────────────


def test_decide_refused_when_step_not_decision_pending():
    async def scenario():
        run = _build("run_test_decide_refused", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
        ])
        res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun", rationale="r")
        assert res["code"] == 409
        assert "not decision_pending" in res["error"]
        res = await orchestrator.decide_step(run.run_id, "step_ghost", action="apply_and_rerun", rationale="r")
        assert res["code"] == 404
    run_async(scenario())


def test_decide_requires_rationale_and_valid_action():
    async def scenario():
        run = _build("run_test_decide_validation", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun", rationale="  ")
        assert res["code"] == 400 and "rationale" in res["error"]
        res = await orchestrator.decide_step(run.run_id, "step_x", action="bogus", rationale="r")
        assert res["code"] == 400 and "action" in res["error"]
        res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun",
                                             strategy_id="nope", rationale="r")
        assert res["code"] == 400 and "unknown strategy" in res["error"]
    run_async(scenario())


def test_strategy_is_single_shot():
    async def scenario():
        run = _build("run_test_single_shot", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"],
                      strategies=[Strategy(id="s1", patches=[StrategyPatch(step_id="step_x", inputs={"a": 1})])]),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        try:
            res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun",
                                                 strategy_id="s1", rationale="first")
            assert res["status"] == "applied"
            step.status = StepStatus.decision_pending  # pretend it failed again
            res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun",
                                                 strategy_id="s1", rationale="again")
            assert res["code"] == 409 and "single-shot" in res["error"]
        finally:
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


# ── (6) autonomy gating of free-form patches ───────────────────────────


def test_free_form_patch_forbidden_unless_manual():
    async def scenario():
        run = _build("run_test_patch_gating", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
        ], autonomy="assisted")
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun",
                                             patch={"inputs": {"a": 1}}, rationale="r")
        assert res["code"] == 403
        assert step.inputs == {}
    run_async(scenario())


def test_free_form_patch_applied_when_manual_and_probes_preserved():
    async def scenario():
        run = _build("run_test_patch_manual", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
        ], autonomy="manual")
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        try:
            # a patch DROPPING a PROBE line is refused even for manual
            res = await orchestrator.decide_step(
                run.run_id, "step_x", action="apply_and_rerun",
                patch={"acceptance_criteria": ["only prose"]}, rationale="r")
            assert res["code"] == 400 and "PROBE" in res["error"]

            res = await orchestrator.decide_step(
                run.run_id, "step_x", action="apply_and_rerun",
                patch={"inputs": {"a": 1}, "acceptance_criteria": ["PROBE: true", "added"]},
                rationale="manual re-parameterization")
            assert res["status"] == "applied"
            assert step.inputs == {"a": 1}
            assert step.acceptance_criteria == ["PROBE: true", "added"]
            assert step.status == StepStatus.ready  # reset by the jump machinery
            assert run.forced_next_step == "step_x"
        finally:
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


# ── (7) halt strategy + arm swap (patch other step, skip decided one) ──


def test_halt_strategy_converts_decision_into_halted_gate():
    async def scenario():
        run = _build("run_test_halt_strategy", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"],
                      strategies=[Strategy(id="manual_review", halt=True)]),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun",
                                             strategy_id="manual_review", rationale="escalate")
        assert res["status"] == "halted"
        assert step.status == StepStatus.halted
        assert step.gate_type == "segmentation"
        assert run.status == RunStatus.paused
        assert step.strategies_applied == ["manual_review"]
    run_async(scenario())


def test_arm_swap_patches_other_step_and_skips_decided_one():
    async def scenario():
        strat = Strategy(id="heuristic_arm", arm_swap=True,
                         patches=[StrategyPatch(step_id="step_group",
                                                acceptance_criteria=["PROBE: test -s grouping.json"])],
                         skip=["step_segment"])
        run = _build("run_test_arm_swap", [
            StepInput(id="step_segment", title="Vision segmentation",
                      acceptance_criteria=["PROBE: ls segment/*.json"], strategies=[strat]),
            StepInput(id="step_group", title="Grouping", depends_on=["step_segment"],
                      acceptance_criteria=["PROBE: true"]),
        ])
        seg, group = run.epics[0].stories[0].steps
        seg.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        try:
            res = await orchestrator.decide_step(run.run_id, "step_segment", action="apply_and_rerun",
                                                 strategy_id="heuristic_arm", rationale="vision unstable, swap arm")
            assert res["status"] == "applied"
            assert res["rerun_from"] == "step_group"
            assert group.status == StepStatus.ready
            assert group.acceptance_criteria == ["PROBE: test -s grouping.json"]
            assert seg.status == StepStatus.done  # skipped ⇒ dependents unblocked
            assert run.forced_next_step == "step_group"
            assert gate_blocked_step(run) is None
        finally:
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


# ── (8) scope rules file ───────────────────────────────────────────────


def test_rules_appended_deduped_with_derived_path(tmp_path):
    async def scenario():
        run = _build("run_test_rules", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"],
                      inputs={"project_path": "projects/testproj", "project": "testproj"}),
        ])
        run.repo_dir = str(tmp_path)
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        hold = asyncio.Event()
        fake_loop = asyncio.create_task(hold.wait())
        orchestrator._active_tasks[run.run_id] = fake_loop
        rule = {"id": "exclude-consent-banner", "action": "exclude",
                "match": {"selector": "#onetrust-banner-sdk"}, "scope": "site",
                "reason": "consent widget, not site content", "decidedBy": "claude", "date": "2026-07-03"}
        try:
            res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun",
                                                 rules=[rule], rationale="declutter segmentation input")
            assert res["status"] == "applied"
            assert res["rules"]["added"] == ["exclude-consent-banner"]
            rf = tmp_path / "projects/testproj/workflow-output/scope-rules.json"
            assert rf.is_file()
            doc = json.loads(rf.read_text())
            assert doc["rules"] == [rule]

            # dedupe by id on re-append
            step.status = StepStatus.decision_pending
            res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun",
                                                 rules=[rule], rationale="again")
            assert res["rules"]["added"] == [] and res["rules"]["skipped"] == ["exclude-consent-banner"]
            assert len(json.loads(rf.read_text())["rules"]) == 1
        finally:
            hold.set()
            await fake_loop
            orchestrator._active_tasks.pop(run.run_id, None)
    run_async(scenario())


def test_rules_refused_without_derivable_path_or_pattern():
    async def scenario():
        run = _build("run_test_rules_refused", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"], inputs={}),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        run.status = RunStatus.paused
        rule = {"id": "r1", "action": "exclude", "match": {"selector": ".x"}}
        res = await orchestrator.decide_step(run.run_id, "step_x", action="apply_and_rerun",
                                             rules=[rule], rationale="r")
        assert res["code"] == 400 and "rules_file" in res["error"]
        # a rule keyed on nothing (no selector/signature) is refused
        run2 = _build("run_test_rules_refused2", [
            StepInput(id="step_y", title="Y", acceptance_criteria=["PROBE: true"],
                      inputs={"project_path": "projects/p"}),
        ])
        step2 = run2.epics[0].stories[0].steps[0]
        step2.status = StepStatus.decision_pending
        res = await orchestrator.decide_step(run2.run_id, "step_y", action="apply_and_rerun",
                                             rules=[{"id": "r2", "match": {"page": "/en/home"}}], rationale="r")
        assert res["code"] == 400 and "pattern-keyed" in res["error"]
    run_async(scenario())


# ── (9) decisions bundle + G-D human answer + C3 cost dir ──────────────


def test_decision_bundle_lists_pending_decision():
    run = _build("run_test_bundle", [
        StepInput(id="step_x", title="X", max_attempts=3, acceptance_criteria=["PROBE: true"],
                  inputs={"project_path": "projects/demo"},
                  strategies=[Strategy(id="s1", order=2), Strategy(id="s0", order=1)]),
    ])
    step = run.epics[0].stories[0].steps[0]
    step.status = StepStatus.decision_pending
    step.attempt = 3
    step.strategies_applied = ["s0"]
    bundles = orchestrator.decision_bundles(run)
    assert len(bundles) == 1
    b = bundles[0]
    assert b["step_id"] == "step_x" and b["review"] is False
    assert b["attempt"] == 3 and b["max_attempts"] == 3
    assert [s["id"] for s in b["strategies_remaining"]] == ["s1"]
    assert b["strategies_applied"] == ["s0"]
    assert b["rules_file_default"] == "projects/demo/workflow-output/scope-rules.json"


def test_human_answer_injected_into_rebuilt_prompt():
    run = _build("run_test_answer_prompt", [
        StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
    ])
    epic, story = run.epics[0], run.epics[0].stories[0]
    step = story.steps[0]
    prompt = build_step_prompt(step, story, epic, run)
    assert "Réponse humaine" not in prompt
    step.human_answer = "utilise le port 8081"
    prompt = build_step_prompt(step, story, epic, run)
    assert "Réponse humaine à ta question précédente: utilise le port 8081" in prompt


def test_submit_human_answer_requeues_step_as_pending():
    async def scenario():
        run = _build("run_test_answer_requeue", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"]),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.waiting_human
        ok = await orchestrator.submit_human_answer(run.run_id, "step_x", "réponse")
        assert ok is True
        # pending, NOT ready: select_next_ready_step only picks pending
        assert step.status == StepStatus.pending
        assert step.human_answer == "réponse"
    run_async(scenario())


def test_cost_dir_is_absolute_and_anchored_on_package():
    assert cost_tracker.DEFAULT_COST_DIR.is_absolute()
    assert cost_tracker.DEFAULT_COST_DIR.parent.name == "migration-orchestrator"
    assert cost_tracker.DEFAULT_COST_DIR.name == "costs"


def test_decision_event_written_to_jsonl_audit_trail(tmp_path):
    # GET /runs/{id}/audit reads the JSONL audit file (stats.py), not the SQLite
    # events table. A decision must appear there too or ?event_type=decision is
    # blind. RunAuditLogger.decision() mirrors the SQLite 'decision' event.
    from src.audit import RunAuditLogger

    logger = RunAuditLogger("run_audit_decision", log_dir=tmp_path)
    logger.decision("e1", "s1", "step_x",
                    {"action": "apply_and_rerun", "strategy_id": "fix_flag",
                     "rationale": "M2 smoke"})
    lines = (tmp_path / "run_audit_decision.jsonl").read_text().splitlines()
    entries = [json.loads(l) for l in lines if l.strip()]
    decisions = [e for e in entries if e.get("event") == "decision"]
    assert len(decisions) == 1
    d = decisions[0]
    assert d["step_id"] == "step_x" and d["epic_id"] == "e1" and d["story_id"] == "s1"
    assert d["strategy_id"] == "fix_flag" and d["rationale"] == "M2 smoke"


# ── (10) decision_pending survives persistence + restart normalization ──


def test_decision_pending_survives_persistence_roundtrip():
    async def scenario():
        run = _build("run_test_decision_persist", [
            StepInput(id="step_x", title="X", acceptance_criteria=["PROBE: true"],
                      strategies=[Strategy(id="s1")]),
        ])
        step = run.epics[0].stories[0].steps[0]
        step.status = StepStatus.decision_pending
        step.strategies_applied = ["s0"]
        run.status = RunStatus.paused
        await persistence.save_run(run)
        loaded = await persistence.load_run(run.run_id)
        lstep = loaded.epics[0].stories[0].steps[0]
        assert lstep.status == StepStatus.decision_pending
        assert lstep.strategies_applied == ["s0"]
        assert [s.id for s in lstep.strategies] == ["s1"]
        assert gate_blocked_step(loaded) is lstep
    run_async(scenario())
