from __future__ import annotations

import asyncio
import logging
import re
import time

from .audit import get_audit_logger
from .cost_tracker import write_run_cost, format_cost_summary
from .models import (
    AgentResult,
    EpicState,
    EpicStatus,
    RunState,
    RunStatus,
    SSEEvent,
    StepState,
    StepStatus,
    StoryState,
    StoryStatus,
)
from .llm_client import LLMClient
from .persistence import load_run, save_event, save_run
from .state import (
    approve_gate_step,
    check_transition,
    find_all_dependents,
    find_decision_steps,
    find_halted_step,
    gate_blocked_step,
    probe_lines,
    get_epic_by_id,
    get_resume_event,
    get_step_by_id,
    get_story_by_id,
    normalize_for_resume,
    reject_gate_step,
    reset_steps_from,
    select_next_ready_step,
    select_next_ready_story,
    all_stories_approved,
    all_steps_done,
)
from .verifier import run_lines, run_step_commands, verify_result

log = logging.getLogger(__name__)

_runs: dict[str, RunState] = {}
_sse_queues: dict[str, list[asyncio.Queue]] = {}
_active_tasks: dict[str, asyncio.Task] = {}


def get_run(run_id: str) -> RunState | None:
    return _runs.get(run_id)


def register_run(run: RunState) -> None:
    _runs[run.run_id] = run


def subscribe_sse(run_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _sse_queues.setdefault(run_id, []).append(queue)
    return queue


def unsubscribe_sse(run_id: str, queue: asyncio.Queue) -> None:
    listeners = _sse_queues.get(run_id, [])
    if queue in listeners:
        listeners.remove(queue)


async def notify_sse(run: RunState, event_type: str, data: dict, **ids) -> None:
    event = SSEEvent(
        type=event_type,
        run_id=run.run_id,
        epic_id=ids.get("epic_id"),
        story_id=ids.get("story_id"),
        step_id=ids.get("step_id"),
        data=data,
    )
    payload = event.model_dump()
    for queue in _sse_queues.get(run.run_id, []):
        await queue.put(payload)
    await save_event(run.run_id, event_type, data, **{k: v for k, v in ids.items() if v})


async def start_run(run: RunState, client: LLMClient, event_listener: object | None = None) -> None:
    register_run(run)
    await save_run(run)
    task = asyncio.create_task(_run_loop(run, client, event_listener))
    _active_tasks[run.run_id] = task


async def _run_loop(run: RunState, client: LLMClient, event_listener: object | None = None) -> None:
    audit = get_audit_logger(run.run_id)
    run_start = time.time() * 1000
    audit.run_started(run.goal, run.model, len(run.epics))
    try:
        for epic in run.epics:
            if epic.status == EpicStatus.approved:
                continue
            run.current_epic_id = epic.id
            epic.status = EpicStatus.running
            await notify_sse(run, "epic_status", {"status": "running"}, epic_id=epic.id)
            await _tag_epic_start(run, epic)
            await _epic_loop(run, epic, client, event_listener)
            if epic.status != EpicStatus.approved:
                # A paused/aborted run left the epic mid-flight (a blocking gate or
                # decision point): DON'T fail the run — it must survive to be resumed
                # (a decision decides the parked step, then the loop re-enters).
                if run.status in (RunStatus.paused, RunStatus.aborted):
                    return
                run.status = RunStatus.failed
                break
        else:
            run.status = RunStatus.completed
            duration = time.time() * 1000 - run_start
            total_steps = sum(len(s.steps) for e in run.epics for s in e.stories)
            failed_steps = sum(1 for e in run.epics for s in e.stories for st in s.steps if st.status == StepStatus.failed)
            audit.run_completed(duration, total_steps, failed_steps)
    except Exception as e:
        log.error(f"Run {run.run_id} error: {e}", exc_info=True)
        run.status = RunStatus.failed
        audit.run_failed(str(e), time.time() * 1000 - run_start)
    finally:
        run.updated_at = time.time() * 1000
        await save_run(run)
        await notify_sse(run, "run_status", {"status": run.status.value})

        # Write cost report
        try:
            steps_data = []
            for epic in run.epics:
                for story in epic.stories:
                    for step in story.steps:
                        steps_data.append({
                            "step_id": step.id,
                            "story_id": story.id,
                            "epic_id": epic.id,
                            "tokens_in": step.tokens_in,
                            "tokens_out": step.tokens_out,
                            "tokens_cache": step.tokens_cache,
                            "duration_ms": step.duration_ms,
                        })
            if steps_data:
                cost_report = write_run_cost(run.run_id, run.model, steps_data)
                summary = format_cost_summary(cost_report)
                log.info(f"\n{summary}")
                await notify_sse(run, "run_cost", cost_report["total"])
        except Exception as e:
            log.warning(f"Failed to write cost report: {e}")

        if run.run_id in _active_tasks:
            del _active_tasks[run.run_id]


# ── Deterministic epic approval (P5.5b — the LLM reviewer is gone) ────────────
# Julian's directive (2026-07-04): DeepSeek exits the control loop entirely. Epic
# approval is now a RULE, not a judgment call: an epic is approved iff every story
# is approved AND every step is done with a passing verification. The reviewer LLM
# ranked below the assistant in the authority ladder anyway, and it hallucinated a
# false diagnosis twice on M4 (§13 Q1). The deterministic PROBEs already judged the
# work — the reviewer added only risk. When the rule does NOT hold, the epic loop
# parks the offending step (decision_pending) and, once decided, RE-ENTERS its own
# while-loop to re-execute and re-judge (A3/M1) — never a silent epic fail.


def _epic_verdicts(epic: EpicState) -> list[dict]:
    """Per-step evidence justifying (or refusing) deterministic approval: the
    audit record of what the gate saw. One row per step across every story."""
    verdicts: list[dict] = []
    for story in epic.stories:
        for step in story.steps:
            v = step.verification
            verdicts.append({
                "step_id": step.id,
                "story_id": story.id,
                "status": step.status.value,
                "verification_passed": bool(v.passed) if v else None,
                "checks": len(v.checks) if v else 0,
                "errors": (v.errors[:5] if v else []),
            })
    return verdicts


def _epic_all_green(epic: EpicState) -> bool:
    """The deterministic approval rule: every step done, and every step that ran a
    verification passed it. A step done via the engine-exec path (synthetic result)
    still carries the PROBE-run VerificationResult, so this is the real gate record."""
    for story in epic.stories:
        for step in story.steps:
            if step.status != StepStatus.done:
                return False
            if step.verification is not None and not step.verification.passed:
                return False
    return True


async def _epic_loop(run: RunState, epic: EpicState, client: LLMClient, event_listener: object | None = None) -> None:
    # A3/M1: this MUST be a loop. _run_loop never re-enters an epic after
    # _epic_loop returns — so after an epic-level park is decided (retry/repatch/
    # apply_and_rerun reset some step to ready/pending), returning here left a
    # running non-approved epic that _run_loop turned into run=failed, with the
    # reset step silently dropped. The loop re-executes the stories instead.
    while True:
        await _execute_epic_stories(run, epic, client, event_listener)

        # If the story loop returned without every story approved, a gate/decision is
        # blocking (halted, rejected, or decision_pending) OR the run was aborted — the
        # run stays paused there and the loop must not fabricate an epic verdict. Only a
        # genuinely stuck epic (no runnable work, no parked gate) fails here.
        if not all_stories_approved(epic):
            if run.status in (RunStatus.paused, RunStatus.aborted):
                return
            epic.status = EpicStatus.failed
            await notify_sse(run, "epic_status", {"status": "failed"}, epic_id=epic.id)
            return

        verdicts = _epic_verdicts(epic)
        if _epic_all_green(epic):
            epic.status = EpicStatus.approved
            get_audit_logger(run.run_id).epic_approved(epic.id, verdicts)
            await save_event(run.run_id, "epic_approved", {"epic_id": epic.id, "verdicts": verdicts}, epic_id=epic.id)
            await notify_sse(run, "epic_status", {"status": "approved", "verdicts": verdicts}, epic_id=epic.id)
            await _tag_epic(run, epic)
            return

        # All stories approved but some step is not green (e.g. a verification the
        # story loop tolerated) → NOT an LLM call: park the first offending step for
        # a decision (assisted → assistant; red → Julian), exactly as retries-
        # exhausted does.
        offender = next(
            ((story, step) for story in epic.stories for step in story.steps
             if step.status != StepStatus.done
             or (step.verification is not None and not step.verification.passed)),
            None,
        )
        if offender is None:
            # unreachable in practice (_epic_all_green false implies an offender)
            epic.status = EpicStatus.failed
            await notify_sse(run, "epic_status", {"status": "failed", "verdicts": verdicts}, epic_id=epic.id)
            return
        story, step = offender
        if not await _park_for_decision(run, epic, story, step, "epic_gate_not_green"):
            return  # aborted while parked
        # The decision reset some step(s) to ready/pending via the jump machinery.
        # Re-open every story whose steps are no longer all done —
        # select_next_ready_story only picks PENDING stories, so without this the
        # re-execution pass would find no work and re-park immediately.
        for s in epic.stories:
            if not all_steps_done(s):
                s.status = StoryStatus.pending
        # loop: re-execute the re-opened stories, then re-judge the epic.


async def _execute_epic_stories(run: RunState, epic: EpicState, client: LLMClient, event_listener: object | None = None) -> None:
    while True:
        story = select_next_ready_story(epic)
        if not story:
            break
        resume = get_resume_event(run.run_id)
        if run.status == RunStatus.paused:
            await resume.wait()
        run.current_story_id = story.id
        story.status = StoryStatus.running
        await notify_sse(run, "story_status", {"status": "running"}, epic_id=epic.id, story_id=story.id)
        await _execute_story_steps(run, epic, story, client, event_listener)
        if all_steps_done(story):
            story.status = StoryStatus.approved
        else:
            story.status = StoryStatus.failed
        await notify_sse(run, "story_status", {"status": story.status.value}, epic_id=epic.id, story_id=story.id)


def _remaining_strategies(step: StepState) -> list:
    """Unconsumed pre-registered strategies, in declared order."""
    return sorted(
        (s for s in step.strategies if s.id not in step.strategies_applied),
        key=lambda s: s.order,
    )


async def _park_for_decision(run: RunState, epic: EpicState, story: StoryState, step: StepState, reason: str) -> bool:
    """Decision point (ASSIST-PLAN §3 A2): set the step decision_pending, pause
    the run like a halted gate, notify SSE, and park until the decide endpoint
    moves the step out of decision_pending (strategy applied via jump machinery,
    or 'proceed' on a review step). Returns False iff the run was aborted."""
    step.status = StepStatus.decision_pending
    # A parked decision (incl. review checkpoints) MUST carry its gate_type so the
    # quality panel routes to the right verdict (model/mirror/…) instead of falling
    # back to the first artifact on disk — a stale reconstruct.json from an earlier
    # pipeline would otherwise mask a fresh model/mirror verdict (observed live).
    if not step.gate_type or step.gate_type == "unknown":
        step.gate_type = _infer_gate_type(step) or "unknown"
    step.completed_at = time.time() * 1000
    if step.started_at:
        step.duration_ms = step.completed_at - step.started_at
    run.status = RunStatus.paused
    run.updated_at = time.time() * 1000
    await save_run(run)
    remaining = _remaining_strategies(step)
    await notify_sse(run, "step_decision", {
        "status": "decision_pending", "reason": reason, "review": step.review,
        "attempt": step.attempt, "max_attempts": step.max_attempts,
        "strategies_remaining": [s.id for s in remaining],
        "strategies_applied": list(step.strategies_applied),
    }, step_id=step.id, story_id=story.id, epic_id=epic.id)
    await notify_sse(run, "run_paused", {"reason": "decision", "step_id": step.id})
    resume = get_resume_event(run.run_id)
    resume.clear()
    # Parked exactly like a halted gate: only POST /runs/{id}/steps/{id}/decide
    # moves the step out of decision_pending; a plain resume never does.
    while True:
        await resume.wait()
        if run.status == RunStatus.aborted:
            return False
        if step.status == StepStatus.decision_pending:
            log.warning(f"Step {step.id}: still decision_pending — resume does not decide; POST /runs/{run.run_id}/steps/{step.id}/decide.")
            run.status = RunStatus.paused
            resume.clear()
            continue
        break
    run.status = RunStatus.running
    return True


async def _execute_story_steps(run: RunState, epic: EpicState, story: StoryState, client: LLMClient, event_listener: object | None = None) -> None:
    while True:
        if run.forced_next_step:
            step = get_step_by_id(story, run.forced_next_step)
            if step:
                run.forced_next_step = None
            else:
                step = select_next_ready_step(story)
        else:
            step = select_next_ready_step(story)

        if not step:
            break

        run.current_step_id = step.id

        # Review steps (ASSIST-PLAN §3 A6) are scheduled decision checkpoints:
        # the engine NEVER sends them to an agent — selection = decision_pending.
        if step.review:
            if not await _park_for_decision(run, epic, story, step, "review"):
                return
            continue

        step.status = StepStatus.ready
        step.attempt += 1  # attempt = 1-based execution counter (max_attempts = total budget)
        await _execute_single_step(run, epic, story, step, client, event_listener)

        if step.status == StepStatus.done:
            transition = check_transition(step, story)
            if transition:
                reset_ids = reset_steps_from(story, transition.to_step_id)
                await notify_sse(run, "step_loop", {"from": step.id, "to": transition.to_step_id, "reset_steps": reset_ids}, step_id=step.id, story_id=story.id, epic_id=epic.id)
                continue
        elif step.status == StepStatus.halted:
            run.status = RunStatus.paused
            await notify_sse(run, "run_paused", {"reason": "halt", "step_id": step.id, "summary": step.agent_result.summary if step.agent_result else ""})
            resume = get_resume_event(run.run_id)
            resume.clear()
            # A halted gate is decided ONLY by the typed gate endpoint (approve →
            # done, reject → rejected) or redone via jump. A plain resume never
            # approves it: the loop stays parked here until the step leaves
            # halted/rejected. A rejected gate behaves like failed-with-no-retries:
            # the run stays paused until the operator jumps/rolls back to redo it.
            while True:
                await resume.wait()
                if run.status == RunStatus.aborted:
                    return
                if step.status == StepStatus.halted:
                    log.warning(f"Step {step.id}: still halted — resume does not approve a gate; POST /runs/{run.run_id}/gate {{approve|reject}} or jump.")
                    run.status = RunStatus.paused
                    resume.clear()
                    continue
                if step.status == StepStatus.rejected:
                    log.warning(f"Step {step.id}: gate rejected — run stays paused until the operator jumps/rolls back to redo it.")
                    run.status = RunStatus.paused
                    resume.clear()
                    continue
                break
            run.status = RunStatus.running
            continue
        elif step.status == StepStatus.failed:
            if step.attempt < step.max_attempts:
                # Back to *pending*, NOT ready: select_next_ready_step only picks
                # pending steps ('ready' is jump's forced state). Setting ready here
                # silently skipped every retry (P4: step_segment died at attempt 1/3).
                step.status = StepStatus.pending
                continue
            # Retries EXHAUSTED → ALWAYS a decision point, never a silent run
            # failure (P5.5b, Julian's directive 3): with pre-registered strategies
            # OR without, the run PAUSES and the operator/assistant decides (retry,
            # repatch, apply a strategy, roll back). DeepSeek is out of the loop —
            # there is no repair agent to fall back to. The failure context (last
            # command, exit code, stderr/stdout tails) is already on step.failure_context
            # for the decision bundle.
            if not await _park_for_decision(run, epic, story, step, "retries_exhausted"):
                return
            continue
        elif step.status == StepStatus.waiting_human:
            # Legacy compat path: no engine step produces a question anymore (the LLM
            # left the loop), but a step manually parked in waiting_human still waits
            # for POST /steps/{id}/answer, which re-queues it as pending.
            await _wait_for_human_answer(step)
            continue
        else:
            return


async def _execute_single_step(run: RunState, epic: EpicState, story: StoryState, step: StepState, client: LLMClient, event_listener: object | None = None) -> None:
    step.status = StepStatus.running
    step.streaming_text = ""
    step.started_at = time.time() * 1000
    audit = get_audit_logger(run.run_id)
    audit.step_started(epic.id, story.id, step.id, step.task_type, step.agent, step.attempt)
    await notify_sse(run, "step_status", {"status": "running", "task_type": step.task_type, "agent": step.agent}, step_id=step.id, story_id=story.id, epic_id=epic.id)

    try:
        # ── engine-executes-Run: doctrine (P5) — NO LLM in the loop (P5.5b) ──
        # A step whose acceptance_criteria carry `Run: <cmd>` lines has a KNOWN
        # deterministic command at plan time. The engine runs those lines ITSELF
        # (same subprocess mechanism as the probes).
        #   • ALL pass (or NO Run: lines) → a synthetic agent="engine" result is
        #     fabricated and the existing verification (probes + integrity belt)
        #     judges the step. There is NO agent session — DeepSeek left the control
        #     loop entirely (Julian's directive 2026-07-04): its repair track record
        #     was zero, transients are covered by retries + idempotence, and a shell
        #     at the weakest tier is pure attack surface.
        #   • one FAILS → the step FAILS with the failure context stashed; retries
        #     re-run it, and once exhausted it becomes a decision_pending (retry /
        #     repatch / rollback), never a silent run failure.
        # Kill-switch ORCHESTRATOR_ENGINE_EXEC_RUN and "no Run: lines" both make
        # run_step_commands a no-op returning (True, [], "").
        records: list[dict] = []
        has_run_lines = bool(run_lines(step.acceptance_criteria))
        if has_run_lines:
            # P0: run/step identity in the child env so tools stamp provenance.
            ok, records, failure_context = await run_step_commands(
                step, run.repo_dir, run.run_id,
                extra_env={"ORCH_RUN_ID": run.run_id, "ORCH_STEP_ID": step.id})
            if not ok:
                # A Run: line failed → the step fails; the failure context is stashed
                # for the decision bundle. No repair agent — the engine drives alone.
                step.failure_context = failure_context
                step.completed_at = time.time() * 1000
                step.duration_ms = step.completed_at - step.started_at if step.started_at else 0
                step.status = StepStatus.failed
                will_retry = step.attempt < step.max_attempts
                audit.step_failed(epic.id, story.id, step.id, step.duration_ms,
                                  "Run: line failed", step.attempt, step.max_attempts, will_retry)
                await save_run(run)
                await notify_sse(run, "step_status",
                                 {"status": "failed", "task_type": step.task_type,
                                  "reason": "run_line_failed"},
                                 step_id=step.id, story_id=story.id, epic_id=epic.id)
                return

        # Every Run: line passed (or there were none) → synthetic engine result. The
        # deterministic PROBEs + integrity belt inside verify_result remain the sole
        # judge. No prompt, no tokens, no LLM call.
        if records:
            cmds = "; ".join(r["command"] for r in records)
            summary = f"engine executed {len(records)} Run: command(s) deterministically: {cmds}"[:500]
        else:
            summary = f"engine step (no Run: lines) — verified by {len(step.acceptance_criteria or [])} acceptance criterion/probes"
        agent_result = AgentResult(
            step_id=step.id, agent="engine", status="completed", summary=summary,
        )
        await notify_sse(run, "step_status",
                         {"status": "engine_executed", "task_type": step.task_type,
                          "commands": len(records), "agent": "engine"},
                         step_id=step.id, story_id=story.id, epic_id=epic.id)
        log.info(f"Step {step.id}: engine step ({len(records)} Run: line(s)) — no LLM, verifying")
        step.agent_result = agent_result
        await _verify_and_finalize(run, epic, story, step, agent_result, audit)

    except Exception as e:
        step.completed_at = time.time() * 1000
        step.duration_ms = step.completed_at - step.started_at if step.started_at else 0
        log.error(f"Step {step.id} error: {e}", exc_info=True)
        step.status = StepStatus.failed
        will_retry = step.attempt < step.max_attempts
        audit.step_failed(epic.id, story.id, step.id, step.duration_ms, str(e), step.attempt, step.max_attempts, will_retry)
        await save_run(run)
        await notify_sse(run, "step_status", {"status": "failed", "task_type": step.task_type, "error": str(e)}, step_id=step.id, story_id=story.id, epic_id=epic.id)


async def _verify_and_finalize(run: RunState, epic: EpicState, story: StoryState, step: StepState,
                               agent_result: AgentResult, audit) -> None:
    """Shared verification + status transition, used by BOTH paths: the normal
    agent path and the engine-executes-Run: path (where agent_result is the
    synthetic engine result). The deterministic PROBEs + integrity belt inside
    verify_result remain the sole judge in either case — the engine executing the
    Run: lines never bypasses the gate, it only skips the LLM that would have
    typed the commands."""
    step.status = StepStatus.verifying
    await notify_sse(run, "step_status", {"status": "verifying", "task_type": step.task_type}, step_id=step.id, story_id=story.id, epic_id=epic.id)

    # P0: same run/step identity for probe subprocesses; P1: the modeled project
    # threads into the integrity belt's site derivation.
    verification = await verify_result(step, agent_result, run.repo_dir, run.run_id,
                                       extra_env={"ORCH_RUN_ID": run.run_id, "ORCH_STEP_ID": step.id},
                                       project=run.project)
    step.verification = verification

    if verification.passed and agent_result.status == "completed":
        step.status = StepStatus.done
        step.completed_at = time.time() * 1000
        step.duration_ms = step.completed_at - step.started_at
        audit.step_completed(epic.id, story.id, step.id, step.duration_ms, step.tokens_in, step.tokens_out, step.cost, agent_result.summary)
        audit.verification_result(epic.id, story.id, step.id, True, verification.checks, verification.errors)
        await save_run(run)
        await notify_sse(run, "step_status", {"status": "done", "task_type": step.task_type}, step_id=step.id, story_id=story.id, epic_id=epic.id)
        await notify_sse(run, "step_completed", {"result": agent_result.model_dump()}, step_id=step.id, story_id=story.id, epic_id=epic.id)
    elif agent_result.status == "halt":
        step.status = StepStatus.halted
        # Every halted step MUST carry a gate_type or it is invisible to the
        # control surface (active_gate filters on a truthy gate_type, and the
        # assistant's monitor watches gate.active). Fall back to "unknown"
        # when inference misses so the step still surfaces as a decidable gate.
        step.gate_type = _infer_gate_type(step) or "unknown"
        step.completed_at = time.time() * 1000
        step.duration_ms = step.completed_at - step.started_at
        audit.step_halted(epic.id, story.id, step.id, agent_result.summary)
        await save_run(run)
        await notify_sse(run, "step_status", {"status": "halted", "task_type": step.task_type, "gate_type": step.gate_type, "summary": agent_result.summary}, step_id=step.id, story_id=story.id, epic_id=epic.id)
    elif agent_result.status == "failed" and agent_result.loop_to:
        step.status = StepStatus.done
        step.completed_at = time.time() * 1000
        step.duration_ms = step.completed_at - step.started_at
        audit.step_completed(epic.id, story.id, step.id, step.duration_ms, step.tokens_in, step.tokens_out, step.cost, f"loop_to={agent_result.loop_to}")
        await save_run(run)
        await notify_sse(run, "step_status", {"status": "done", "task_type": step.task_type, "loop_to": agent_result.loop_to}, step_id=step.id, story_id=story.id, epic_id=epic.id)
    else:
        step.status = StepStatus.failed
        step.completed_at = time.time() * 1000
        step.duration_ms = step.completed_at - step.started_at
        # Stash the probe/verification failure so a later decision_pending bundle
        # carries the real reason (no repair agent gets it anymore).
        if verification.errors:
            step.failure_context = "Verification failed:\n" + "\n".join(verification.errors)[:2000]
        will_retry = step.attempt < step.max_attempts
        audit.step_failed(epic.id, story.id, step.id, step.duration_ms, f"agent_status={agent_result.status}", step.attempt, step.max_attempts, will_retry)
        audit.verification_result(epic.id, story.id, step.id, verification.passed, verification.checks, verification.errors)
        await save_run(run)
        await notify_sse(run, "step_status", {"status": "failed", "task_type": step.task_type}, step_id=step.id, story_id=story.id, epic_id=epic.id)


def _infer_gate_type(step: StepState) -> str | None:
    """Map a halted step to a migration-profile gate panel (frontend routing).
    Matched on step id + title ONLY — acceptance criteria embed project paths
    ("projects/contentful/…"), which poison broad substring matches."""
    idt = f"{step.id or ''} {step.title or ''}".lower()
    if "deploy" in idt:
        return "deploy"
    if re.search(r"ground.?truth|live.?fidelity", idt):
        return "groundtruth"
    if "reconstruct" in idt or "fidelity" in idt:
        return "fidelity"
    if "localize" in idt or "mirror" in idt:
        return "mirror"
    if "component_model" in idt or "step_model" in idt or "group" in idt or "cnd" in idt or ("component" in idt and "model" in idt):
        return "model"
    if "visual" in idt or "vanity" in idt or "go-live" in idt or "golive" in idt:
        return "golive"
    if "content" in idt and "extract" not in idt:
        return "content"
    # Analyze/extract phase (e.g. step_content_extract, step_extract): NOT the
    # content-load gate (guarded above) — these belong to the scope/analyze panel.
    if "scope" in idt or "analyze" in idt or "crawl" in idt or "extract" in idt:
        return "scope"
    return None


# P5.5b: the LLM epic reviewer and its rectification-proposal protocol were
# removed. Epic approval is deterministic (_epic_loop). The reviewer OVERRULED
# protocol and the approve/reject-proposal endpoints are gone with it; persisted
# run blobs still deserialize (pending_proposal/review_history stay on the model
# as compat-read fields).


async def pause_run(run_id: str) -> bool:
    run = get_run(run_id)
    if not run or run.status != RunStatus.running:
        return False
    run.status = RunStatus.paused
    resume = get_resume_event(run_id)
    resume.clear()
    await notify_sse(run, "run_paused", {})
    return True


async def resume_run(run_id: str) -> bool:
    run = get_run(run_id)
    if not run or run.status != RunStatus.paused:
        return False
    blocked = gate_blocked_step(run)
    if blocked:
        log.warning(f"Run {run_id}: step {blocked.id} is {blocked.status.value} — resume never decides a gate; approve/reject via POST /runs/{run_id}/gate, or jump/rollback to redo the step.")
        return False
    run.status = RunStatus.running
    resume = get_resume_event(run_id)
    resume.set()
    await notify_sse(run, "run_resumed", {})
    return True


async def try_resume_run(run_id: str, client: LLMClient, event_listener: object | None = None) -> bool:
    run = get_run(run_id)
    # Resume a paused run, and also RECOVER a failed one in place: _run_loop skips
    # already-approved epics and never re-runs done steps (select_next_ready_step
    # only picks ready steps), so recovery continues from the first unfinished
    # step without redoing completed work or re-prompting passed gates.
    if not run or run.status not in (RunStatus.paused, RunStatus.failed):
        return False
    blocked = gate_blocked_step(run)
    if blocked:
        # A halted gate awaits approve/reject; a rejected gate awaits jump/rollback.
        # Either way, a plain resume must never decide it (the run stays paused).
        log.warning(f"Run {run_id}: step {blocked.id} is {blocked.status.value} — resume never decides a gate; approve/reject via POST /runs/{run_id}/gate, or jump/rollback to redo the step.")
        return False
    run.status = RunStatus.running
    if run_id in _active_tasks and not _active_tasks[run_id].done():
        resume = get_resume_event(run_id)
        resume.set()
    else:
        # Fresh loop (engine restarted / loop gone): the in-flight resume handling
        # can't fire, so normalize orphaned/failed state or the loop dies instantly.
        # See normalize_for_resume — halted/rejected gates are refused above.
        normalize_for_resume(run)
        task = asyncio.create_task(_run_loop(run, client, event_listener))
        _active_tasks[run_id] = task
    await notify_sse(run, "run_resumed", {})
    return True


async def _resolve_registered_run(run_id: str) -> RunState | None:
    run = get_run(run_id)
    if not run:
        run = await load_run(run_id)
        if run:
            register_run(run)
    return run


async def approve_gate(run_id: str, client: LLMClient, event_listener: object | None = None) -> dict:
    """The ONLY path that turns a halted gate into done: mark the step approved,
    persist, then resume the run (in-flight loop or a fresh one)."""
    run = await _resolve_registered_run(run_id)
    if not run:
        return {"error": "run not found"}
    epic, story, step = find_halted_step(run)
    if not step:
        return {"error": "no halted gate step"}
    approve_gate_step(step)
    run.updated_at = time.time() * 1000
    await save_run(run)
    await notify_sse(run, "step_status", {"status": "done", "task_type": step.task_type, "gate_decision": "approve"}, step_id=step.id, story_id=story.id, epic_id=epic.id)
    await notify_sse(run, "step_completed", {"result": step.agent_result.model_dump() if step.agent_result else {}}, step_id=step.id, story_id=story.id, epic_id=epic.id)
    if run_id in _active_tasks and not _active_tasks[run_id].done():
        run.status = RunStatus.running
        get_resume_event(run_id).set()
        await notify_sse(run, "run_resumed", {})
    else:
        await try_resume_run(run_id, client, event_listener)
    return {"status": "approved", "step_id": step.id}


async def reject_gate(run_id: str, reason: str = "") -> dict:
    """Persistent gate rejection: the halted step becomes 'rejected' (saved), and
    the run stays paused — like a failed step with no retries left — until the
    operator jumps/rolls back to redo it. Resume never overrides this."""
    run = await _resolve_registered_run(run_id)
    if not run:
        return {"error": "run not found"}
    epic, story, step = find_halted_step(run)
    if not step:
        return {"error": "no halted gate step"}
    reject_gate_step(step)
    run.status = RunStatus.paused
    run.updated_at = time.time() * 1000
    await save_run(run)
    await notify_sse(run, "step_status", {"status": "rejected", "task_type": step.task_type, "gate_type": step.gate_type, "reason": reason}, step_id=step.id, story_id=story.id, epic_id=epic.id)
    return {"status": "rejected", "step_id": step.id, "reason": reason}


async def jump_to_step(
    run_id: str,
    step_id: str,
    epic_id: str | None = None,
    reset_dependents: bool = True,
    client: LLMClient | None = None,
    event_listener: object | None = None,
    skip_done: list[str] | None = None,
) -> dict:
    """Force the run to redo a step (the ONLY documented redo path for a
    rejected gate; also the reset machinery for /decide strategies). Works with
    an in-flight loop (wakes it) or after an engine restart (spawns a fresh
    loop, like try_resume_run). skip_done marks the given steps done AFTER the
    dependent reset (strategy 'skip' semantics — e.g. an arm swap that skips
    step_segment)."""
    run = await _resolve_registered_run(run_id)
    if not run:
        return {"error": "run not found"}

    target_epic = None
    target_story = None
    target_step = None

    for epic in run.epics:
        if epic_id and epic.id != epic_id:
            continue
        for story in epic.stories:
            step = get_step_by_id(story, step_id)
            if step:
                target_epic = epic
                target_story = story
                target_step = step
                break
        if target_step:
            break

    if not target_step or not target_story or not target_epic:
        return {"error": "step not found"}

    reset_ids = [step_id]
    if reset_dependents:
        dependents = find_all_dependents(target_story, step_id)
        for dep_id in dependents:
            dep = get_step_by_id(target_story, dep_id)
            if dep:
                dep.status = StepStatus.pending
                dep.agent_result = None
                dep.verification = None
                dep.streaming_text = ""
                dep.attempt = 0
                dep.failure_context = None
                reset_ids.append(dep_id)

    target_step.status = StepStatus.ready
    target_step.agent_result = None
    target_step.verification = None
    target_step.streaming_text = ""
    target_step.attempt = 0
    target_step.failure_context = None

    skipped: list[str] = []
    for skip_id in skip_done or []:
        for epic in run.epics:
            for story in epic.stories:
                sk = get_step_by_id(story, skip_id)
                if sk:
                    sk.status = StepStatus.done
                    sk.completed_at = time.time() * 1000
                    skipped.append(skip_id)

    run.forced_next_step = step_id
    run.current_epic_id = target_epic.id
    run.current_story_id = target_story.id
    run.current_step_id = step_id

    if run_id in _active_tasks and not _active_tasks[run_id].done():
        # In-flight loop (possibly parked on a halted/rejected gate): the target
        # step just left halted/rejected, so waking the loop lets it proceed.
        if run.status == RunStatus.paused:
            run.status = RunStatus.running
        get_resume_event(run_id).set()
    else:
        # Engine restarted / loop gone: forced_next_step alone leaves a zombie
        # run (nothing consumes it, and a later resume is refused while the run
        # claims running). Spawn a fresh loop like try_resume_run does. The
        # normalization turns the target's 'ready' into 'pending' — harmless,
        # forced_next_step routes to it regardless of status.
        run.status = RunStatus.running
        normalize_for_resume(run)
        task = asyncio.create_task(_run_loop(run, client, event_listener))
        _active_tasks[run_id] = task

    run.updated_at = time.time() * 1000
    await save_run(run)
    await notify_sse(run, "step_jumped", {"step_id": step_id, "reset_steps": reset_ids, "skipped_steps": skipped}, step_id=step_id, story_id=target_story.id, epic_id=target_epic.id)
    return {"status": "jump_scheduled", "step_id": step_id, "reset_steps": reset_ids, "skipped_steps": skipped}


# ── Decision protocol (ASSIST-PLAN §3) ────────────────────────────────
# A decision_pending step is decided ONLY here: apply a pre-registered strategy
# (patches + skips + reset via the jump machinery), proceed a review step, or
# (manual autonomy only) apply a free-form patch. Every decision is audited.


_PROJECT_PATH_RE = re.compile(r"^projects/[\w-]+")


def derive_rules_file(step: StepState) -> str | None:
    """Default scope-rules file from the step's inputs: any input value matching
    ^projects/<name> → <PP>/workflow-output/scope-rules.json."""
    for v in step.inputs.values():
        if isinstance(v, str):
            m = _PROJECT_PATH_RE.match(v)
            if m:
                return f"{m.group(0)}/workflow-output/scope-rules.json"
    return None


def append_scope_rules(repo_dir: str, rules_file: str, rules: list[dict]) -> dict:
    """Append rules (deduped by rule id) to the scope-rules file
    ({"rules": [...]}, ASSIST-PLAN §5). Returns {path, added, skipped}."""
    import json
    from pathlib import Path

    path = Path(rules_file)
    if not path.is_absolute():
        path = Path(repo_dir) / rules_file
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"rules": []}
    if path.is_file():
        try:
            doc = json.loads(path.read_text())
        except Exception:
            doc = {"rules": []}
    existing = {r.get("id") for r in doc.get("rules", [])}
    added, skipped = [], []
    for rule in rules:
        rid = rule.get("id")
        if rid in existing:
            skipped.append(rid)
            continue
        doc.setdefault("rules", []).append(rule)
        existing.add(rid)
        added.append(rid)
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return {"path": str(path), "added": added, "skipped": skipped}


def _find_step_anywhere(run: RunState, step_id: str) -> tuple[EpicState | None, StoryState | None, StepState | None]:
    for epic in run.epics:
        for story in epic.stories:
            step = get_step_by_id(story, step_id)
            if step:
                return epic, story, step
    return None, None, None


async def _resume_after_decision(run: RunState, client: LLMClient | None, event_listener: object | None = None) -> None:
    """Resume a run whose decision step just left decision_pending: wake the
    parked in-flight loop, or spawn a fresh one after an engine restart."""
    if run.run_id in _active_tasks and not _active_tasks[run.run_id].done():
        run.status = RunStatus.running
        get_resume_event(run.run_id).set()
        await notify_sse(run, "run_resumed", {})
    else:
        await try_resume_run(run.run_id, client, event_listener)


async def decide_step(
    run_id: str,
    step_id: str,
    *,
    action: str,
    rationale: str,
    strategy_id: str | None = None,
    rules: list[dict] | None = None,
    rules_file: str | None = None,
    patch: dict | None = None,
    rerun_from: str | None = None,
    repatch_step_id: str | None = None,
    repatch_inputs: dict | None = None,
    repatch_extra: dict | None = None,
    client: LLMClient | None = None,
    event_listener: object | None = None,
) -> dict:
    """Decide a decision_pending step (POST /runs/{id}/steps/{id}/decide).
    Returns {"error", "code"} on refusal, else a success dict. Semantics:
      - action=proceed (review steps only) → step done, run resumes;
      - action=retry → reset the step's attempts and re-queue it as-is (P5.5b);
      - action=repatch {inputs} → merge inputs into the step (NEVER
        acceptance_criteria / PROBE lines — U4/amendment 4b), reset attempts, re-queue;
      - action=apply_and_rerun + strategy_id → apply the strategy's patches/skips
        (or halt), reset via jump machinery. Single-shot per strategy.
      - action=apply_and_rerun + patch (free-form) → autonomy=manual ONLY; PROBE preserved.
      - rules → appended (deduped by id) to the scope-rules file, whatever the action.
    """
    run = await _resolve_registered_run(run_id)
    if not run:
        return {"error": "run not found", "code": 404}
    epic, story, step = _find_step_anywhere(run, step_id)
    if not step:
        return {"error": "step not found", "code": 404}
    if step.status != StepStatus.decision_pending:
        return {"error": f"step {step_id} is '{step.status.value}', not decision_pending — nothing to decide", "code": 409}
    if not (rationale or "").strip():
        return {"error": "rationale is required", "code": 400}
    if action not in ("apply_and_rerun", "proceed", "retry", "repatch"):
        return {"error": "action must be apply_and_rerun|proceed|retry|repatch", "code": 400}
    if patch is not None and strategy_id is not None:
        return {"error": "provide either strategy_id or patch, not both", "code": 400}
    if patch is not None and getattr(run, "autonomy", "assisted") != "manual":
        return {"error": "free-form patch is allowed only when run.autonomy == 'manual' (assisted picks from the registered strategy list)", "code": 403}

    # Scope rules (ASSIST-PLAN §5) — appended whatever the action (a review
    # checkpoint may emit rules then proceed).
    rules_result = None
    if rules:
        for rule in rules:
            if not rule.get("id"):
                return {"error": "every rule needs an 'id'", "code": 400}
            match = rule.get("match") or {}
            if not (match.get("selector") or match.get("signature")):
                return {"error": f"rule '{rule['id']}': match must be pattern-keyed (selector or signature), never a page URL", "code": 400}
        rf = rules_file or derive_rules_file(step)
        if not rf:
            return {"error": "rules given but no rules_file derivable from the step's inputs (no projects/<name> path) and none provided", "code": 400}
        rules_result = append_scope_rules(run.repo_dir, rf, rules)

    audit_payload = {
        "step_id": step_id, "action": action, "rationale": rationale,
        "strategy_id": strategy_id, "patch": patch, "rerun_from": rerun_from,
        "rules": rules_result, "autonomy": getattr(run, "autonomy", "assisted"),
    }

    if action == "proceed":
        if not step.review:
            return {"error": "proceed is only valid on review steps", "code": 400}
        step.status = StepStatus.done
        step.completed_at = time.time() * 1000
        run.updated_at = time.time() * 1000
        await save_run(run)
        await save_event(run_id, "decision", audit_payload, step_id=step_id, story_id=story.id, epic_id=epic.id)
        get_audit_logger(run_id).decision(epic.id, story.id, step_id, audit_payload)
        await notify_sse(run, "step_status", {"status": "done", "task_type": step.task_type, "decision": "proceed"}, step_id=step_id, story_id=story.id, epic_id=epic.id)
        await _resume_after_decision(run, client, event_listener)
        return {"status": "proceeded", "step_id": step_id, "rules": rules_result}

    # ── retry (P5.5b): reset attempts + re-queue the step UNCHANGED ──────────
    # No strategy, no patch — just give the same step a fresh attempt budget and
    # send it back through the loop. For transients the engine already covers
    # (retries + idempotence); the operator uses this after fixing the world
    # out-of-band (a Jahia restart, a freed disk) and wants the run to continue.
    if action == "retry":
        if strategy_id is not None or patch is not None or rules is not None:
            return {"error": "retry takes no strategy_id/patch/rules — it re-runs the step as-is", "code": 400}
        step.failure_context = None
        await save_event(run_id, "decision", audit_payload, step_id=step_id, story_id=story.id, epic_id=epic.id)
        get_audit_logger(run_id).decision(epic.id, story.id, step_id, audit_payload)
        result = await jump_to_step(run_id, step_id, None, True, client=client, event_listener=event_listener)
        if result.get("error"):
            return {"error": result["error"], "code": 400}
        return {"status": "retried", "step_id": step_id, "jump": result}

    # ── repatch (P5.5b, U4 / amendment 4b): merge INPUTS then re-queue ───────
    # The assistant re-parameterizes the step at the decision point — `inputs`
    # ONLY. acceptance_criteria (and its PROBE: lines) are frozen bars that a
    # patch may NEVER touch (rule-1 lint), so repatch refuses acceptance_criteria
    # AND any field other than inputs. Merge (not replace) so the operator only
    # sends the keys that change. Allowed in ANY autonomy (it cannot move a bar).
    if action == "repatch":
        if strategy_id is not None or patch is not None:
            return {"error": "repatch takes `inputs` only — not strategy_id/patch", "code": 400}
        target_step_id = repatch_step_id or step_id
        if not isinstance(repatch_inputs, dict):
            return {"error": "repatch requires an `inputs` object", "code": 400}
        forbidden = set(repatch_extra or {})
        if forbidden:
            return {"error": "repatch merges `inputs` only — these fields are refused: "
                    + ", ".join(sorted(forbidden)) + " (acceptance_criteria/PROBE: lines are frozen bars — rule 1)", "code": 400}
        _, _, ts = _find_step_anywhere(run, target_step_id)
        if not ts:
            return {"error": f"repatch targets unknown step '{target_step_id}'", "code": 400}
        before = dict(ts.inputs or {})
        merged = {**before, **repatch_inputs}
        ts.inputs = merged
        ts.failure_context = None
        # A3/M2 (mirror of apply_and_rerun): when the repatch targets ANOTHER step,
        # the DECIDED step must leave decision_pending BEFORE the jump wakes the
        # parked loop — otherwise the loop sees it still decision_pending, re-parks
        # it, the repatched step is never consumed, and gate_blocked_step keeps
        # refusing every resume (total wedge). Re-queue it as pending with fresh
        # attempts; it re-runs naturally after the repatched target.
        if target_step_id != step_id:
            step.status = StepStatus.pending
            step.attempt = 0
        audit_payload["repatch"] = {
            "step_id": target_step_id, "inputs_before": before, "inputs_after": merged,
            "keys_changed": sorted(k for k in merged if before.get(k) != merged.get(k)),
        }
        await save_event(run_id, "decision", audit_payload, step_id=step_id, story_id=story.id, epic_id=epic.id)
        get_audit_logger(run_id).decision(epic.id, story.id, step_id, audit_payload)
        result = await jump_to_step(run_id, target_step_id, None, True, client=client, event_listener=event_listener)
        if result.get("error"):
            return {"error": result["error"], "code": 400}
        return {"status": "repatched", "step_id": step_id, "target_step_id": target_step_id,
                "inputs": merged, "rules": rules_result, "jump": result}

    # apply_and_rerun
    skip_ids: list[str] = []
    rerun_target = rerun_from or step_id
    if strategy_id is not None:
        strategy = next((s for s in step.strategies if s.id == strategy_id), None)
        if not strategy:
            return {"error": f"unknown strategy '{strategy_id}' on step {step_id}", "code": 400}
        if strategy.id in step.strategies_applied:
            return {"error": f"strategy '{strategy_id}' already consumed (single-shot)", "code": 409}
        step.strategies_applied.append(strategy.id)

        if strategy.halt:
            # manual_review class: the decision becomes a halted gate for Julian.
            step.status = StepStatus.halted
            step.gate_type = "segmentation"
            run.status = RunStatus.paused
            run.updated_at = time.time() * 1000
            await save_run(run)
            await save_event(run_id, "decision", {**audit_payload, "halt": True}, step_id=step_id, story_id=story.id, epic_id=epic.id)
            get_audit_logger(run_id).decision(epic.id, story.id, step_id, {**audit_payload, "halt": True})
            await notify_sse(run, "step_status", {"status": "halted", "task_type": step.task_type, "gate_type": step.gate_type, "summary": f"strategy {strategy.id}: escalated to human review"}, step_id=step_id, story_id=story.id, epic_id=epic.id)
            return {"status": "halted", "step_id": step_id, "strategy": strategy.id, "gate_type": "segmentation", "rules": rules_result}

        for p in strategy.patches:
            _, _, ps = _find_step_anywhere(run, p.step_id)
            if not ps:
                return {"error": f"strategy patch targets unknown step '{p.step_id}'", "code": 400}
            if p.inputs is not None:
                ps.inputs = dict(p.inputs)
            if p.acceptance_criteria is not None:
                ps.acceptance_criteria = list(p.acceptance_criteria)
        skip_ids = list(strategy.skip)
        if rerun_from is None and step_id in skip_ids and strategy.patches:
            # arm swap: the decided step itself is skipped — rerun from the patched arm
            rerun_target = strategy.patches[0].step_id
        audit_payload["patched_steps"] = [p.step_id for p in strategy.patches]
        audit_payload["skipped_steps"] = skip_ids

    elif patch is not None:
        p_step_id = patch.get("step_id") or step_id
        _, _, ps = _find_step_anywhere(run, p_step_id)
        if not ps:
            return {"error": f"patch targets unknown step '{p_step_id}'", "code": 400}
        new_criteria = patch.get("acceptance_criteria")
        if new_criteria is not None:
            missing = [l for l in probe_lines(ps.acceptance_criteria) if l not in new_criteria]
            if missing:
                return {"error": "patch removes or modifies PROBE line(s) — frozen bars never move: " + "; ".join(m[:120] for m in missing), "code": 400}
            ps.acceptance_criteria = list(new_criteria)
        if patch.get("inputs") is not None:
            ps.inputs = dict(patch["inputs"])
        rerun_target = rerun_from or p_step_id
    # else: rules-only decision — rerun the decided step against the new rules.

    # Leave decision_pending BEFORE the jump wakes the parked loop: if the rerun
    # target is elsewhere and the step is neither reset by the jump nor skipped,
    # it must not stay parked as decision_pending.
    if step_id != rerun_target and step_id not in skip_ids:
        step.status = StepStatus.pending
        step.attempt = 0

    await save_event(run_id, "decision", audit_payload, step_id=step_id, story_id=story.id, epic_id=epic.id)
    get_audit_logger(run_id).decision(epic.id, story.id, step_id, audit_payload)
    result = await jump_to_step(run_id, rerun_target, None, True, client=client, event_listener=event_listener, skip_done=skip_ids)
    if result.get("error"):
        return {"error": result["error"], "code": 400}
    return {"status": "applied", "step_id": step_id, "strategy": strategy_id,
            "rerun_from": rerun_target, "rules": rules_result, "jump": result}


def decision_bundles(run: RunState) -> list[dict]:
    """GET /runs/{id}/decisions — the full decision bundle per pending step so the
    assistant (or Julian) can decide WITHOUT the conversation context (P5.5b: the
    LLM is out of the loop, so the bundle IS the failure record):
      - identity, attempts history, strategies remaining/applied;
      - the step's stashed failure_context (last Run: failure or verification errors);
      - probe verdicts (command, exit code, stdout/stderr ~800c tails) AND the last
        engine-run command_executed events (Run: line that failed), from the audit trail;
      - the last verification result, inputs and acceptance criteria."""
    import json
    from pathlib import Path

    bundles = []
    for epic, story, step in find_decision_steps(run):
        probes: list[dict] = []
        commands: list[dict] = []
        try:
            audit_file = Path("/tmp/orch-audit") / f"{run.run_id}.jsonl"
            if audit_file.is_file():
                for line in audit_file.read_text().splitlines():
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if ev.get("step_id") != step.id:
                        continue
                    if ev.get("event") == "probe_executed":
                        probes.append({
                            "command": ev.get("command"), "exit_code": ev.get("exit_code"),
                            "passed": ev.get("passed"),
                            "stdout_tail": (ev.get("stdout") or "")[-800:],
                            "stderr_tail": (ev.get("stderr") or "")[-800:],
                            "ts": ev.get("ts"),
                        })
                    elif ev.get("event") == "command_executed":
                        commands.append({
                            "command": ev.get("command"), "exit_code": ev.get("exit_code"),
                            "passed": ev.get("passed"),
                            "stdout_tail": (ev.get("stdout") or "")[-800:],
                            "stderr_tail": (ev.get("stderr") or "")[-800:],
                            "ts": ev.get("ts"),
                        })
        except Exception:
            pass
        remaining = _remaining_strategies(step)
        bundles.append({
            "step_id": step.id, "title": step.title, "epic_id": epic.id, "story_id": story.id,
            "review": step.review,
            "reason": ("review" if step.review else "retries_exhausted"),
            "attempt": step.attempt, "max_attempts": step.max_attempts,
            "inputs": step.inputs,
            "acceptance_criteria": step.acceptance_criteria,
            "failure_context": step.failure_context,
            "strategies_remaining": [s.model_dump() for s in remaining],
            "strategies_applied": list(step.strategies_applied),
            "verification": step.verification.model_dump() if step.verification else None,
            "agent_summary": step.agent_result.summary if step.agent_result else None,
            "probes": probes[-5:],
            "commands": commands[-5:],
            "next_actions": (["proceed"] if step.review
                             else ["retry", "repatch"] + (["decide(strategy)"] if remaining else []) + ["rollback", "restart"]),
            "rules_file_default": derive_rules_file(step),
        })
    return bundles


async def restart_run(run_id: str, client: LLMClient, event_listener: object | None = None) -> dict:
    run = get_run(run_id)
    if not run:
        run = await load_run(run_id)
    if not run:
        return {"error": "run not found"}
    register_run(run)
    from .models import RunStatus
    for epic in run.epics:
        epic.status = EpicStatus.pending
        epic.review_round = 0
        epic.review_history = []
        epic.pending_proposal = None
        for story in epic.stories:
            story.status = StoryStatus.pending
            for step in story.steps:
                step.status = StepStatus.pending
                step.agent_result = None
                step.verification = None
                step.streaming_text = ""
                step.attempt = 0
                step.question = None
                step.human_answer = None
                step.failure_context = None
                step.strategies_applied = []
    run.status = RunStatus.running
    run.current_epic_id = None
    run.current_story_id = None
    run.current_step_id = None
    run.forced_next_step = None
    run.updated_at = time.time() * 1000
    await save_run(run)
    task = asyncio.create_task(_run_loop(run, client, event_listener))
    _active_tasks[run.run_id] = task
    return {"status": "restarted", "run_id": run_id}


# ── Granular restart: a single epic or story (not the whole run) ──────────────
# Recovery for a stalled/failed epic or story without re-running approved work.
# _run_loop skips approved epics and select_next_ready_* only picks pending items,
# so resetting the target back to pending makes the loop re-enter exactly it.

def _reset_step(step: StepState) -> None:
    step.status = StepStatus.pending
    step.agent_result = None
    step.verification = None
    step.streaming_text = ""
    step.attempt = 0
    step.question = None
    step.human_answer = None
    step.failure_context = None
    step.strategies_applied = []


def _reset_story_state(story: StoryState) -> None:
    story.status = StoryStatus.pending
    story.current_step_index = 0
    for step in story.steps:
        _reset_step(step)


def _reset_epic_full(epic: EpicState) -> None:
    epic.status = EpicStatus.pending
    epic.review_round = 0
    epic.review_history = []
    epic.pending_proposal = None
    for story in epic.stories:
        _reset_story_state(story)


def _reopen_epic(epic: EpicState) -> None:
    """Mark an epic re-enterable WITHOUT touching its stories (used by restart_story
    so approved sibling stories stay approved while the loop re-reviews the epic)."""
    epic.status = EpicStatus.pending
    epic.review_round = 0
    epic.review_history = []
    epic.pending_proposal = None


def _story_dependents(epic: EpicState, story_id: str) -> set[str]:
    """Transitive stories within the epic whose depends_on chain reaches story_id."""
    deps = {story_id}
    changed = True
    while changed:
        changed = False
        for s in epic.stories:
            if s.id in deps:
                continue
            if any(d in deps for d in s.depends_on):
                deps.add(s.id)
                changed = True
    deps.discard(story_id)
    return deps


async def _relaunch_loop(run: RunState, client: LLMClient, event_listener: object | None = None) -> None:
    """Cancel any in-flight loop task, then start a fresh one from the reset state."""
    old = _active_tasks.get(run.run_id)
    if old and not old.done():
        old.cancel()
        try:
            await old
        except BaseException:
            pass
    run.status = RunStatus.running
    run.current_epic_id = None
    run.current_story_id = None
    run.current_step_id = None
    run.forced_next_step = None
    run.updated_at = time.time() * 1000
    await save_run(run)
    task = asyncio.create_task(_run_loop(run, client, event_listener))
    _active_tasks[run.run_id] = task


async def restart_epic(run_id: str, epic_id: str, client: LLMClient, event_listener: object | None = None) -> dict:
    run = get_run(run_id)
    if not run:
        run = await load_run(run_id)
    if not run:
        return {"error": "run not found"}
    register_run(run)
    epic = get_epic_by_id(run, epic_id)
    if not epic:
        return {"error": "epic not found"}
    _reset_epic_full(epic)
    await _relaunch_loop(run, client, event_listener)
    await notify_sse(run, "epic_restarted", {"epic_id": epic_id}, epic_id=epic_id)
    return {"status": "epic_restarted", "epic_id": epic_id}


async def restart_story(run_id: str, epic_id: str, story_id: str, client: LLMClient, event_listener: object | None = None) -> dict:
    run = get_run(run_id)
    if not run:
        run = await load_run(run_id)
    if not run:
        return {"error": "run not found"}
    register_run(run)
    epic = get_epic_by_id(run, epic_id)
    if not epic:
        return {"error": "epic not found"}
    story = get_story_by_id(epic, story_id)
    if not story:
        return {"error": "story not found"}
    targets = {story_id} | _story_dependents(epic, story_id)
    for s in epic.stories:
        if s.id in targets:
            _reset_story_state(s)
    _reopen_epic(epic)  # re-enter + re-review; approved sibling stories stay approved
    await _relaunch_loop(run, client, event_listener)
    await notify_sse(
        run, "story_restarted",
        {"epic_id": epic_id, "story_id": story_id, "reset_stories": sorted(targets)},
        epic_id=epic_id, story_id=story_id,
    )
    return {"status": "story_restarted", "epic_id": epic_id, "story_id": story_id, "reset_stories": sorted(targets)}


async def abort_run(run_id: str) -> bool:
    run = get_run(run_id)
    if not run:
        return False
    run.status = RunStatus.aborted
    audit = get_audit_logger(run_id)
    audit.run_aborted()
    resume = get_resume_event(run_id)
    resume.set()
    await save_run(run)  # persist aborted status so list/prune see it correctly
    await notify_sse(run, "run_status", {"status": "aborted"})
    return True


async def delete_run(run_id: str) -> bool:
    """Permanently remove a run: cancel its task if active, drop it from the
    in-memory registry, and delete its rows (run + events) from the database. A
    running run is cancelled first so its loop cannot keep writing after the
    delete. Returns False only when the run id is unknown in both memory and DB."""
    task = _active_tasks.pop(run_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    in_memory = _runs.pop(run_id, None) is not None
    if in_memory:
        # release anything blocked on this run's resume gate
        get_resume_event(run_id).set()
    from .persistence import delete_run as _db_delete_run
    deleted = await _db_delete_run(run_id)
    return deleted or in_memory


async def prune_runs() -> list[str]:
    """Delete all finished runs (completed/failed/aborted) and return their ids.
    Active runs (created/running/paused) are kept. The in-memory registry and any
    leftover tasks for the pruned runs are cleaned up too."""
    from .persistence import delete_finished_runs
    deleted = await delete_finished_runs()
    for rid in deleted:
        task = _active_tasks.pop(rid, None)
        if task and not task.done():
            task.cancel()
        _runs.pop(rid, None)
    return deleted


async def _tag_epic_start(run: RunState, epic: EpicState) -> None:
    tag = f"epic-{epic.id}-start"
    msg = f"Orchestration {run.run_id}: début epic {epic.id} — {epic.title}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "tag", "-a", tag, "-m", msg,
            cwd=run.repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        log.info(f"Tag {tag} created at start of epic {epic.id}")
    except Exception as e:
        log.warning(f"Failed to create start tag for epic {epic.id}: {e}")


async def _tag_epic(run: RunState, epic: EpicState) -> None:
    tag = f"epic-{epic.id}-approved"
    msg = f"Orchestration {run.run_id}: epic {epic.id} approuvé — {epic.title} (round {epic.review_round})"
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "tag", "-a", tag, "-m", msg,
            cwd=run.repo_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        log.info(f"Tag {tag} created on approval of epic {epic.id}")
    except Exception as e:
        log.warning(f"Failed to create approval tag for epic {epic.id}: {e}")


async def submit_human_answer(run_id: str, step_id: str, answer: str) -> bool:
    run = get_run(run_id)
    if not run:
        return False
    for epic in run.epics:
        for story in epic.stories:
            step = get_step_by_id(story, step_id)
            if step and step.status == StepStatus.waiting_human:
                step.human_answer = answer
                # pending, NOT ready: after _wait_for_human_answer the loop
                # re-selects via select_next_ready_step, which only picks pending.
                step.status = StepStatus.pending
                return True
    return False


async def _wait_for_human_answer(step: StepState) -> None:
    while step.status == StepStatus.waiting_human:
        await asyncio.sleep(0.5)
