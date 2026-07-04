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
    NewStepProposal,
    RectificationProposal,
    RunState,
    RunStatus,
    SSEEvent,
    StepState,
    StepStatus,
    StoryInput,
    StoryState,
    StoryStatus,
)
from .llm_client import LLMClient
from .persistence import load_run, save_event, save_run
from .prompt_builder import build_step_prompt
from .repair_agent import review_epic_direct, run_repair_agent
from .question_detector import detect_question
from .rectification_detector import parse_epic_review_result
from .state import (
    approve_gate_step,
    build_step_state,
    build_story_state,
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
from .verifier import parse_agent_result, run_lines, run_step_commands, verify_result

log = logging.getLogger(__name__)

_runs: dict[str, RunState] = {}
_sse_queues: dict[str, list[asyncio.Queue]] = {}
_proposal_events: dict[str, asyncio.Event] = {}
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


async def _epic_loop(run: RunState, epic: EpicState, client: LLMClient, event_listener: object | None = None) -> None:
    while True:
        await _execute_epic_stories(run, epic, client, event_listener)
        if not all_stories_approved(epic):
            epic.status = EpicStatus.failed
            await notify_sse(run, "epic_status", {"status": "failed"}, epic_id=epic.id)
            return

        epic.status = EpicStatus.reviewing
        await notify_sse(run, "epic_status", {"status": "reviewing"}, epic_id=epic.id)
        epic.review_round += 1

        review_result = await _review_epic(run, epic, client, event_listener)
        if review_result is None:
            # Resilient mode: a review that the model couldn't produce a parseable
            # verdict for (hang/timeout/non-JSON) must NOT kill a run whose actual
            # work was gated by the step PROBEs. Auto-approve and continue.
            log.warning(f"Epic {epic.id}: review returned no parseable verdict; auto-approving (resilient mode).")
            epic.status = EpicStatus.approved
            await notify_sse(run, "epic_status", {"status": "approved", "note": "auto-approved: review unparseable"}, epic_id=epic.id)
            await _tag_epic(run, epic)
            return

        epic.review_history.append({
            "round": epic.review_round,
            "result": review_result.model_dump(),
            "timestamp": time.time() * 1000,
        })
        await notify_sse(run, "review_result", {"round": epic.review_round, "result": review_result.model_dump()}, epic_id=epic.id)

        if hasattr(review_result, "summary"):
            epic.status = EpicStatus.approved
            await notify_sse(run, "epic_status", {"status": "approved"}, epic_id=epic.id)
            await _tag_epic(run, epic)
            return

        if epic.review_round >= epic.review_config.max_review_rounds:
            if epic.review_config.auto_approve_on_max_rounds:
                epic.status = EpicStatus.approved
                await notify_sse(run, "epic_status", {"status": "approved"}, epic_id=epic.id)
                await _tag_epic(run, epic)
            else:
                epic.status = EpicStatus.failed
                await notify_sse(run, "epic_status", {"status": "failed"}, epic_id=epic.id)
            return

        proposal = RectificationProposal(
            proposal_id=f"prop_{run.run_id}_{epic.id}_{epic.review_round}",
            epic_id=epic.id,
            round=epic.review_round,
            result=review_result,
            timestamp=time.time() * 1000,
        )
        epic.pending_proposal = proposal
        epic.status = EpicStatus.waiting_approval
        await notify_sse(run, "rectification_proposed", {"proposal": proposal.model_dump()}, epic_id=epic.id)

        await _wait_for_proposal_decision(run, epic)

        if epic.pending_proposal.status == "rejected":
            # OVERRULE semantics (P5): the human/assistant rejects the REVIEWER's
            # rectification proposal, not the epic. The steps were already judged
            # by deterministic probes and audited HALT approvals — a higher
            # authority than the reviewer LLM (which can hallucinate failure from
            # a halted-then-approved gate, seen live on M4). Rejecting a proposal
            # therefore approves the epic as-is; failing the run requires an
            # explicit rollback/abort, never a proposal rejection.
            epic.status = EpicStatus.approved
            epic.pending_proposal = None
            await notify_sse(run, "epic_status",
                             {"status": "approved", "review": "rectification rejected — reviewer overruled"},
                             epic_id=epic.id)
            await _tag_epic(run, epic)
            return

        _inject_rectification_stories(epic, review_result)
        epic.pending_proposal = None
        epic.status = EpicStatus.running
        await notify_sse(run, "epic_status", {"status": "running"}, epic_id=epic.id)


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
            if _remaining_strategies(step):
                # Retries exhausted WITH strategies left → decision point, not failure.
                if not await _park_for_decision(run, epic, story, step, "retries_exhausted"):
                    return
                continue
            return
        elif step.status == StepStatus.waiting_human:
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
        # ── engine-executes-Run: doctrine (P5) ──────────────────────────────
        # A step whose acceptance_criteria carry `Run: <cmd>` lines has a KNOWN
        # deterministic command at plan time. The engine runs those lines ITSELF
        # (same subprocess mechanism as the probes) BEFORE any agent session.
        #   • ALL pass  → NO agent session is opened; a synthetic engine
        #                 agent_result is fabricated and the existing verification
        #                 (probes + integrity belt) still judges the step.
        #   • one FAILS → the agent session opens as today, but with the failure
        #                 context appended to the prompt — the LLM is a REPAIRER,
        #                 not the executant.
        # Kill-switch ORCHESTRATOR_ENGINE_EXEC_RUN and "no Run: lines" both make
        # run_step_commands a no-op returning (True, [], "") → legacy path intact.
        run_failure: str | None = None
        has_run_lines = bool(run_lines(step.acceptance_criteria))
        if has_run_lines:
            ok, records, failure_context = await run_step_commands(step, run.repo_dir, run.run_id)
            if ok and records:
                # Every Run: line passed → skip the agent entirely. The LLM would
                # only re-run commands the engine already proved (the 2×600s
                # read-loop incident). Verification below remains the judge.
                cmds = "; ".join(r["command"] for r in records)
                agent_result = AgentResult(
                    step_id=step.id,
                    agent="engine",
                    status="completed",
                    summary=f"engine executed {len(records)} Run: command(s) deterministically: {cmds}"[:500],
                )
                await notify_sse(run, "step_status",
                                 {"status": "engine_executed", "task_type": step.task_type,
                                  "commands": len(records), "agent": "engine"},
                                 step_id=step.id, story_id=story.id, epic_id=epic.id)
                log.info(f"Step {step.id}: engine ran {len(records)} Run: line(s) OK — agent skipped")
                step.agent_result = agent_result
                return await _verify_and_finalize(run, epic, story, step, agent_result, audit)
            if not ok:
                # A Run: line failed → open the agent as a repairer with context.
                run_failure = failure_context
                log.info(f"Step {step.id}: a Run: line failed — opening repair agent with failure context")

        # ── RÉPARATEUR: in-engine tool loop via the direct LLM API (P5.5) ────
        # Replaces the opencode session/polling/permission machinery. The model
        # chooses read_file/bash/write_file; the ENGINE executes them (same
        # subprocess+env path as probes/Run:); the final JSON envelope is parsed
        # exactly as before. Token usage is accumulated per chat() call into the
        # step counters + per-project ledger inside run_repair_agent → llm_cost.
        prompt = build_step_prompt(step, story, epic, run, run_failure=run_failure)
        step.prompt_text = prompt[:5000]
        audit.step_prompt_sent(epic.id, story.id, step.id, prompt, "direct")

        result_text = await run_repair_agent(
            run=run, epic=epic, story=story, step=step, prompt=prompt,
            client=client, model=run.model,
        )

        if result_text is None:
            log.warning(f"Step {step.id}: repair agent produced no result text")
            step.status = StepStatus.failed
            return

        log.info(f"Step {step.id}: got result_text ({len(result_text)} chars)")

        question = detect_question(result_text, step.id)
        if question:
            step.question = question
            step.status = StepStatus.waiting_human
            await notify_sse(run, "human_question", {"question": question.model_dump()}, step_id=step.id, story_id=story.id, epic_id=epic.id)
            return

        agent_result = parse_agent_result(result_text, step)
        if agent_result is None:
            log.warning(f"Step {step.id}: parse_agent_result returned None, creating fallback from raw text ({len(result_text)} chars)")
            agent_result = AgentResult(
                step_id=step.id,
                agent=step.agent,
                status="completed",
                summary=result_text[:500],
            )

        log.info(f"Step {step.id}: agent_result status={agent_result.status} summary={agent_result.summary[:100]}")

        step.agent_result = agent_result
        # Cost: token counters were accumulated per chat() call; compute the
        # dollar cost from them so /runs/{id}/stats reflects the direct-API spend.
        try:
            from .cost_tracker import calculate_cost
            step.cost = calculate_cost(step.tokens_in, step.tokens_out, step.tokens_cache, run.model)["cost_total"]
            log.info(f"Step {step.id}: tokens in={step.tokens_in} out={step.tokens_out} cache={step.tokens_cache} cost=${step.cost:.4f}")
        except Exception as e:
            log.warning(f"Step {step.id}: failed to compute cost: {e}")

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

    verification = await verify_result(step, agent_result, run.repo_dir, run.run_id)
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


async def _review_epic(run: RunState, epic: EpicState, client: LLMClient, event_listener: object | None = None):
    """Epic review via a SINGLE direct API call (P5.5) — no tools, json_object
    forced. review_epic_direct returns the raw JSON text; parse_epic_review_result
    turns it into a verdict (None on failure → the caller's resilient auto-approve).
    The 'reviewer OVERRULED' protocol downstream is unchanged."""
    result_text = await review_epic_direct(run, epic, client, model=run.model)
    if result_text is None:
        return None
    return parse_epic_review_result(result_text)


async def _wait_for_proposal_decision(run: RunState, epic: EpicState) -> None:
    key = f"{run.run_id}:{epic.id}"
    event = asyncio.Event()
    _proposal_events[key] = event
    await event.wait()
    del _proposal_events[key]


async def approve_proposal(run_id: str, epic_id: str) -> bool:
    run = get_run(run_id)
    if not run:
        return False
    epic = get_epic_by_id(run, epic_id)
    if not epic or not epic.pending_proposal:
        return False
    epic.pending_proposal.status = "approved"
    key = f"{run_id}:{epic_id}"
    if key in _proposal_events:
        _proposal_events[key].set()
    return True


async def reject_proposal(run_id: str, epic_id: str) -> bool:
    run = get_run(run_id)
    if not run:
        return False
    epic = get_epic_by_id(run, epic_id)
    if not epic or not epic.pending_proposal:
        return False
    epic.pending_proposal.status = "rejected"
    key = f"{run_id}:{epic_id}"
    if key in _proposal_events:
        _proposal_events[key].set()
    return True


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
                reset_ids.append(dep_id)

    target_step.status = StepStatus.ready
    target_step.agent_result = None
    target_step.verification = None
    target_step.streaming_text = ""
    target_step.attempt = 0

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
    client: LLMClient | None = None,
    event_listener: object | None = None,
) -> dict:
    """Decide a decision_pending step (POST /runs/{id}/steps/{id}/decide).
    Returns {"error", "code"} on refusal, else a success dict. Semantics:
      - action=proceed (review steps only) → step done, run resumes;
      - strategy_id → apply the strategy's patches/skips (or halt), reset via
        jump machinery (reset_dependents), resume. Single-shot per strategy.
      - patch (free-form) → autonomy=manual ONLY; PROBE lines must be preserved.
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
    if action not in ("apply_and_rerun", "proceed"):
        return {"error": "action must be apply_and_rerun|proceed", "code": 400}
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
    """GET /runs/{id}/decisions — the full decision bundle per pending step:
    identity, attempts, strategies remaining/applied, verification (incl. probe
    stdout/stderr tails from the audit trail), inputs and criteria."""
    bundles = []
    for epic, story, step in find_decision_steps(run):
        probes = []
        try:
            import json
            from pathlib import Path
            audit_file = Path("/tmp/orch-audit") / f"{run.run_id}.jsonl"
            if audit_file.is_file():
                for line in audit_file.read_text().splitlines():
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if ev.get("event") == "probe_executed" and ev.get("step_id") == step.id:
                        probes.append({
                            "command": ev.get("command"), "exit_code": ev.get("exit_code"),
                            "passed": ev.get("passed"),
                            "stdout_tail": (ev.get("stdout") or "")[-1000:],
                            "stderr_tail": (ev.get("stderr") or "")[-1000:],
                            "ts": ev.get("ts"),
                        })
        except Exception:
            pass
        remaining = _remaining_strategies(step)
        bundles.append({
            "step_id": step.id, "title": step.title, "epic_id": epic.id, "story_id": story.id,
            "review": step.review,
            "attempt": step.attempt, "max_attempts": step.max_attempts,
            "inputs": step.inputs,
            "acceptance_criteria": step.acceptance_criteria,
            "strategies_remaining": [s.model_dump() for s in remaining],
            "strategies_applied": list(step.strategies_applied),
            "verification": step.verification.model_dump() if step.verification else None,
            "agent_summary": step.agent_result.summary if step.agent_result else None,
            "probes": probes[-5:],
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
                step.opencode_session_id = None
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
    step.opencode_session_id = None
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


def _inject_rectification_stories(epic: EpicState, review) -> None:
    for new_story in review.new_stories:
        story_input = StoryInput(
            id=new_story.id,
            title=new_story.title,
            description=new_story.description,
            acceptance_criteria=new_story.acceptance_criteria,
            depends_on=new_story.depends_on,
            github_issues=new_story.github_issues,
            steps=[
                StepInput(
                    id=s.id,
                    title=s.title,
                    task_type=s.task_type,
                    agent=s.agent,
                    depends_on=s.depends_on,
                    inputs={**s.inputs, "_rectification_reason": s.reason, "_rectification_diagnosis": review.diagnosis},
                    expected_outputs=s.expected_outputs,
                    acceptance_criteria=s.acceptance_criteria,
                )
                for s in new_story.steps
            ] if new_story.steps else [],
        )
        story_state = build_story_state(story_input)

        if review.target_after_story_id:
            idx = next(i for i, s in enumerate(epic.stories) if s.id == review.target_after_story_id)
            epic.stories.insert(idx + 1, story_state)
        else:
            epic.stories.append(story_state)
