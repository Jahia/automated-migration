from __future__ import annotations

import asyncio
import logging
import time

from .audit import get_audit_logger
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
from .opencode_client import OpenCodeClient
from .opencode_events import OpenCodeEventListener
from .persistence import load_run, save_event, save_run
from .prompt_builder import build_review_epic_prompt, build_step_prompt
from .question_detector import detect_question
from .rectification_detector import parse_epic_review_result
from .state import (
    build_step_state,
    build_story_state,
    check_transition,
    find_all_dependents,
    get_epic_by_id,
    get_resume_event,
    get_step_by_id,
    get_story_by_id,
    reset_steps_from,
    select_next_ready_step,
    select_next_ready_story,
    all_stories_approved,
    all_steps_done,
)
from .verifier import parse_agent_result, verify_result

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


async def start_run(run: RunState, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> None:
    register_run(run)
    await save_run(run)
    task = asyncio.create_task(_run_loop(run, client, event_listener))
    _active_tasks[run.run_id] = task


async def _run_loop(run: RunState, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> None:
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
        if run.run_id in _active_tasks:
            del _active_tasks[run.run_id]


async def _epic_loop(run: RunState, epic: EpicState, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> None:
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
            epic.status = EpicStatus.failed
            epic.pending_proposal = None
            await notify_sse(run, "epic_status", {"status": "failed"}, epic_id=epic.id)
            return

        _inject_rectification_stories(epic, review_result)
        epic.pending_proposal = None
        epic.status = EpicStatus.running
        await notify_sse(run, "epic_status", {"status": "running"}, epic_id=epic.id)


async def _execute_epic_stories(run: RunState, epic: EpicState, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> None:
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


async def _execute_story_steps(run: RunState, epic: EpicState, story: StoryState, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> None:
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
        step.status = StepStatus.ready
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
            await resume.wait()
            run.status = RunStatus.running
            # Resuming from a halt is the operator's approval of the gate: mark the
            # step done so its dependents unblock. Without this the step stays
            # 'halted', select_next_ready_step finds nothing, and the story fails.
            # (To redo a halted step instead of approving it, use jump, which resets it.)
            if step.status == StepStatus.halted:
                step.status = StepStatus.done
                await notify_sse(run, "step_status", {"status": "done", "task_type": step.task_type}, step_id=step.id, story_id=story.id, epic_id=epic.id)
                await notify_sse(run, "step_completed", {"result": step.agent_result.model_dump() if step.agent_result else {}}, step_id=step.id, story_id=story.id, epic_id=epic.id)
            continue
        elif step.status == StepStatus.failed:
            if step.attempt < step.max_attempts:
                step.attempt += 1
                step.status = StepStatus.ready
                continue
            # Attempts exhausted: ESCALATE to the operator instead of killing the
            # run — one stubborn page must not stop everything behind it. The
            # operator can answer with instructions (attempts reset, the answer is
            # injected into the next prompt) or "skip" to accept and move on.
            errs = "; ".join(str(e)[:200] for e in (step.verification.errors[:2] if step.verification else []))
            from .models import HumanQuestion
            step.question = HumanQuestion(
                question_id=f"exhausted_{step.id}_{int(time.time())}",
                step_id=step.id,
                question=(f"L'étape '{step.title}' a épuisé ses {step.max_attempts} tentatives. "
                          f"Dernières erreurs: {errs or '(voir vérification)'} — "
                          "Répondez avec des instructions pour réessayer (tentatives réinitialisées), "
                          "ou 'skip' pour accepter l'état actuel et continuer."),
                options=[{"value": "skip", "label": "Accepter et continuer"}],
                timestamp=time.time() * 1000,
            )
            step.status = StepStatus.waiting_human
            await save_run(run)
            await notify_sse(run, "human_question", {"question": step.question.model_dump()}, step_id=step.id, story_id=story.id, epic_id=epic.id)
            await _wait_for_human_answer(step)
            step.question = None
            if (step.human_answer or "").strip().lower() == "skip":
                step.status = StepStatus.done
                await notify_sse(run, "step_status", {"status": "done", "task_type": step.task_type, "note": "skipped by operator after exhausted attempts"}, step_id=step.id, story_id=story.id, epic_id=epic.id)
                continue
            step.attempt = 0  # fresh budget, operator guidance rides in the prompt
            step.status = StepStatus.ready
            continue
        elif step.status == StepStatus.waiting_human:
            await _wait_for_human_answer(step)
            continue
        else:
            return


async def _execute_single_step(run: RunState, epic: EpicState, story: StoryState, step: StepState, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> None:
    step.status = StepStatus.running
    step.streaming_text = ""
    step.started_at = time.time() * 1000
    audit = get_audit_logger(run.run_id)
    audit.step_started(epic.id, story.id, step.id, step.task_type, step.agent, step.attempt)
    await notify_sse(run, "step_status", {"status": "running", "task_type": step.task_type, "agent": step.agent}, step_id=step.id, story_id=story.id, epic_id=epic.id)

    try:
        # ── Deterministic step: task_type "script" ────────────────────────────
        # No LLM session is opened. The work IS the command(s) in
        # step.inputs.script (string or list); the verifier executes them plus
        # every PROBE from acceptance_criteria, in order, and the step passes
        # only if all exit 0. Use for steps that must not be improvised
        # (extract/media/loaders/wiring/gate batteries). Fully source-agnostic:
        # the plan supplies the commands, the engine just runs them.
        if step.task_type == "script":
            script = step.inputs.get("script") or []
            if isinstance(script, str):
                script = [script]
            probes = [
                c.strip()[len("PROBE:"):].strip()
                for c in step.acceptance_criteria
                if c.strip().startswith("PROBE:")
            ]
            if not script and not probes:
                raise ValueError(f"script step {step.id} has no inputs.script and no PROBE criteria")
            agent_result = AgentResult(
                step_id=step.id,
                agent="script",
                status="completed",
                summary=("script: " + " && ".join(script))[:300] if script else "deterministic step: probes only",
                commands_requested=script + probes,
            )
            step.agent_result = agent_result
            step.status = StepStatus.verifying
            await notify_sse(run, "step_status", {"status": "verifying", "task_type": step.task_type}, step_id=step.id, story_id=story.id, epic_id=epic.id)
            verification = await verify_result(step, agent_result, run.repo_dir, run.run_id)
            step.verification = verification
            step.completed_at = time.time() * 1000
            step.duration_ms = step.completed_at - step.started_at
            if verification.passed:
                step.status = StepStatus.done
                audit.step_completed(epic.id, story.id, step.id, step.duration_ms, 0, 0, 0.0, agent_result.summary)
                audit.verification_result(epic.id, story.id, step.id, True, verification.checks, verification.errors)
                await save_run(run)
                await notify_sse(run, "step_status", {"status": "done", "task_type": step.task_type}, step_id=step.id, story_id=story.id, epic_id=epic.id)
                await notify_sse(run, "step_completed", {"result": agent_result.model_dump()}, step_id=step.id, story_id=story.id, epic_id=epic.id)
            else:
                step.status = StepStatus.failed
                will_retry = step.attempt < step.max_attempts
                audit.step_failed(epic.id, story.id, step.id, step.duration_ms, "script/probe command failed", step.attempt, step.max_attempts, will_retry)
                audit.verification_result(epic.id, story.id, step.id, False, verification.checks, verification.errors)
                await save_run(run)
                await notify_sse(run, "step_status", {"status": "failed", "task_type": step.task_type}, step_id=step.id, story_id=story.id, epic_id=epic.id)
            return

        session = await client.create_session(title=f"{story.id} - {step.task_type}", directory=run.repo_dir)
        step.opencode_session_id = session["id"]

        prompt = build_step_prompt(step, story, epic, run)
        step.prompt_text = prompt[:5000]
        audit.step_prompt_sent(epic.id, story.id, step.id, prompt, session["id"])

        queue = event_listener.subscribe(session["id"])
        try:
            await client.send_prompt_async(session["id"], prompt, agent=step.agent, directory=run.repo_dir)
            result_text = await _wait_for_step_completion(session["id"], queue, step, run, story, epic, client)
        finally:
            event_listener.unsubscribe(session["id"], queue)

        if result_text is None:
            log.warning(f"Step {step.id}: result_text is None, trying to extract from messages")
            try:
                msgs = await client.get_messages(step.opencode_session_id)
                # Collect all assistant text and reasoning
                all_text = ""
                for m in reversed(msgs):
                    if m.get("info", {}).get("role") != "assistant":
                        continue
                    for p in reversed(m.get("parts", [])):
                        txt = p.get("text", "") or ""
                        if p.get("type") in ("text", "reasoning") and txt:
                            all_text = txt + "\n" + all_text
                if all_text:
                    # Try to extract JSON from the concatenated text
                    from .verifier import extract_json
                    json_str = extract_json(all_text)
                    if json_str:
                        result_text = json_str
                        log.info(f"Step {step.id}: recovered JSON from reasoning ({len(json_str)} chars)")
                    else:
                        result_text = all_text
                        log.info(f"Step {step.id}: recovered raw text from reasoning ({len(all_text)} chars)")
                else:
                    log.warning(f"Step {step.id}: no assistant text found in messages")
            except Exception as e:
                log.warning(f"Step {step.id}: recovery failed: {e}")

        if result_text is None:
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

        # Fetch token usage and cost from the session
        try:
            sess_detail = await client.http.get(f"/session/{step.opencode_session_id}")
            if sess_detail.status_code == 200:
                sd = sess_detail.json()
                t = sd.get("tokens", {})
                step.tokens_in = t.get("input", 0)
                step.tokens_out = t.get("output", 0)
                step.tokens_cache = t.get("cache", {}).get("read", 0) if isinstance(t.get("cache"), dict) else 0
                step.cost = sd.get("cost", 0.0)
                log.info(f"Step {step.id}: tokens in={step.tokens_in} out={step.tokens_out} cache={step.tokens_cache} cost=${step.cost:.4f}")
        except Exception as e:
            log.warning(f"Step {step.id}: failed to fetch tokens: {e}")
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
            step.completed_at = time.time() * 1000
            step.duration_ms = step.completed_at - step.started_at
            audit.step_halted(epic.id, story.id, step.id, agent_result.summary)
            await save_run(run)
            await notify_sse(run, "step_status", {"status": "halted", "task_type": step.task_type, "summary": agent_result.summary}, step_id=step.id, story_id=story.id, epic_id=epic.id)
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

    except Exception as e:
        step.completed_at = time.time() * 1000
        step.duration_ms = step.completed_at - step.started_at if step.started_at else 0
        log.error(f"Step {step.id} error: {e}", exc_info=True)
        step.status = StepStatus.failed
        will_retry = step.attempt < step.max_attempts
        audit.step_failed(epic.id, story.id, step.id, step.duration_ms, str(e), step.attempt, step.max_attempts, will_retry)
        await save_run(run)
        await notify_sse(run, "step_status", {"status": "failed", "task_type": step.task_type, "error": str(e)}, step_id=step.id, story_id=story.id, epic_id=epic.id)


def _latest_assistant_text(msgs: list) -> str:
    """Concatenate the text parts of the most recent assistant message."""
    for m in reversed(msgs):
        if m.get("info", {}).get("role") != "assistant":
            continue
        texts = [p.get("text", "") for p in m.get("parts", []) if p.get("type") == "text" and p.get("text")]
        if texts:
            return "\n".join(texts)
    return ""


def _latest_assistant_stream(msgs: list) -> str:
    """Latest assistant message rendered for the LIVE LOG window: text parts as-is,
    reasoning parts prefixed with a marker so the UI can show the model *thinking*
    even when it never emits a final text part (the reasoning-only stall we hit on
    build steps). Display-only — result harvesting still uses the raw messages."""
    for m in reversed(msgs):
        if m.get("info", {}).get("role") != "assistant":
            continue
        out: list[str] = []
        for p in m.get("parts", []):
            t = p.get("type")
            txt = p.get("text", "") or ""
            if not txt:
                continue
            if t == "text":
                out.append(txt)
            elif t == "reasoning":
                # prefix each reasoning line with the brain marker so the live-log
                # UI can dim it (and so a reasoning-only stall is still visible)
                out.append("\n".join("\U0001f9e0 " + ln for ln in txt.splitlines()))
        if out:
            return "\n".join(out)
    return ""


def _assistant_turn_complete(msgs: list) -> bool:
    """True when the most recent assistant message has finished. opencode sets
    info.time.completed once a turn (including its tool calls) is done. NOTE: this
    is true at EVERY turn boundary, not only at final session idle — an agent that
    emits a short preamble turn then continues (or spawns subagents) will momentarily
    look 'complete'. Callers must debounce with _session_fingerprint to avoid
    harvesting mid-task. See _wait_for_step_completion."""
    for m in reversed(msgs):
        info = m.get("info", {})
        if info.get("role") == "assistant":
            return bool(info.get("time", {}).get("completed"))
    return False


def _session_fingerprint(msgs: list) -> tuple:
    """A cheap signature of the conversation state: message count, last message id,
    and total text length. It changes whenever a new turn starts or text grows, so
    a stable fingerprint across consecutive polls means the agent has genuinely gone
    quiet (not just paused at a turn boundary)."""
    total_text = 0
    for m in msgs:
        for p in m.get("parts", []):
            if p.get("type") in ("text", "reasoning"):
                total_text += len(p.get("text", "") or "")
    last_id = msgs[-1].get("info", {}).get("id", "") if msgs else ""
    return (len(msgs), last_id, total_text)


async def _wait_for_step_completion(
    session_id: str,
    queue: asyncio.Queue,
    step: StepState,
    run: RunState,
    story: StoryState,
    epic: EpicState,
    client: OpenCodeClient,
) -> str | None:
    """Wait for the opencode session to truly finish, then return the final
    assistant text. The primary signal is the session.idle event; because that
    event feed is unreliable for directory-scoped sessions, a polling fallback
    treats the agent as done only when the last turn is complete AND the
    conversation fingerprint has been stable for QUIESCE_POLLS consecutive polls.
    The debounce is essential: info.time.completed flips true at every turn
    boundary, so without it a short preamble turn (or a pause while subagents run)
    would be harvested as the final result. Whichever signal fires first wins, so a
    dead event feed no longer forces the full timeout. Streams text deltas to the
    UI best-effort and auto-approves permission prompts; the deadline is a hard
    backstop, not the common case. It is configurable because real steps vary by
    orders of magnitude: a content slice iterating toward pixel parity
    (build + deploy + probe per cycle) legitimately needs 30-45 min, while a
    connectivity check needs 2. Order of precedence: step.inputs._deadline_s
    (plan-level knob, underscore = engine-only, hidden from the prompt) >
    ORCH_STEP_DEADLINE_S env > 1800s default. On deadline the harvest is
    mid-work: step.timed_out is set so the retry prompt tells the agent the
    session was cut (work is idempotent — it resumes, not restarts)."""
    import os
    last_text = ""
    poll_every = 3.0
    try:
        deadline = float(step.inputs.get("_deadline_s") or os.environ.get("ORCH_STEP_DEADLINE_S") or 1800.0)
    except (TypeError, ValueError):
        deadline = 1800.0
    step.timed_out = False
    elapsed = 0.0
    QUIESCE_POLLS = 7  # ~21s of no change after a completed turn => genuinely idle
    last_fp: tuple | None = None
    stable = 0

    async def _stream(msgs: list) -> None:
        nonlocal last_text
        # Live log includes reasoning (prefixed) so the window shows the model
        # thinking even when it emits no final text part.
        txt = _latest_assistant_stream(msgs)
        if txt and len(txt) > len(last_text):
            delta = txt[len(last_text):]
            last_text = txt
            step.streaming_text = txt
            await notify_sse(run, "step_streaming", {"delta": delta, "text": txt}, step_id=step.id, story_id=story.id, epic_id=epic.id)

    while True:
        # 1. React to events promptly when they arrive (streaming, permissions, idle).
        try:
            event = await asyncio.wait_for(queue.get(), timeout=poll_every)
        except asyncio.TimeoutError:
            event = None

        if event is not None:
            et = event.get("type", "")
            if et == "permission.updated":
                pid = event.get("properties", {}).get("id", "")
                if pid:
                    await client.respond_permission(session_id, pid, "always")
                continue
            if et == "session.idle":
                try:
                    msgs = await client.get_messages(session_id)
                    txt = _latest_assistant_text(msgs)
                except Exception:
                    txt = ""
                return txt or last_text or None
            try:
                await _stream(await client.get_messages(session_id))
            except Exception:
                pass
            continue

        # 2. No event this window — polling fallback with debounce (works even if
        # the event feed is dead, without harvesting at an intermediate turn).
        elapsed += poll_every
        try:
            msgs = await client.get_messages(session_id)
        except Exception:
            msgs = None
        if msgs:
            await _stream(msgs)
            fp = _session_fingerprint(msgs)
            if _assistant_turn_complete(msgs) and fp == last_fp:
                stable += 1
                if stable >= QUIESCE_POLLS:
                    return _latest_assistant_text(msgs) or last_text or None
            else:
                stable = 0
            last_fp = fp

        if elapsed >= deadline:
            step.timed_out = True
            log.warning(f"Step {step.id}: session deadline {deadline:.0f}s reached — harvesting mid-work text")
            return last_text or None


async def _wait_for_completion_poll(
    session_id: str,
    step: StepState,
    run: RunState,
    story: StoryState,
    epic: EpicState,
    client: OpenCodeClient,
    poll_interval: int = 1,
    max_polls: int = 180,
) -> str | None:
    last_text = ""
    last_reasoning_len = 0
    step.streaming_text = ""
    reasoning_stable = 0
    text_stable = 0

    for poll_count in range(max_polls):
        await asyncio.sleep(poll_interval)

        try:
            msgs_resp = await client.http.get(f"/session/{session_id}/message", params={"limit": 5})
            if msgs_resp.status_code == 200:
                msgs = msgs_resp.json()
                has_step_finish = False
                has_step_start = False
                current_reasoning_len = 0

                for m in msgs:
                    if m.get("info", {}).get("role") != "assistant":
                        continue
                    parts = m.get("parts", [])
                    for p in parts:
                        if p.get("type") == "text":
                            full_text = p.get("text", "")
                            if len(full_text) > len(last_text):
                                delta = full_text[len(last_text):]
                                last_text = full_text
                                step.streaming_text = full_text
                                text_stable = 0
                                await notify_sse(run, "step_streaming", {"delta": delta, "text": full_text}, step_id=step.id, story_id=story.id, epic_id=epic.id)
                        if p.get("type") == "reasoning":
                            current_reasoning_len += len(p.get("text", "") or "")
                        if p.get("type") == "step-finish":
                            has_step_finish = True
                        if p.get("type") == "step-start":
                            has_step_start = True

                # Text stability: if text exists and unchanged for 10s, done
                if last_text:
                    text_stable += 1
                    if text_stable >= 10:
                        return last_text
                else:
                    text_stable = 0

                # Reasoning stability: if reasoning stopped growing for 15s and step-finish exists, session is done
                if current_reasoning_len > last_reasoning_len:
                    last_reasoning_len = current_reasoning_len
                    reasoning_stable = 0
                elif current_reasoning_len > 0:
                    reasoning_stable += 1

                if has_step_finish and reasoning_stable >= 15:
                    return last_text or None

        except Exception as e:
            log.warning(f"Poll error for step {step.id}: {e}")

    return step.streaming_text or last_text or None


async def _review_epic(run: RunState, epic: EpicState, client: OpenCodeClient, event_listener: OpenCodeEventListener):
    prompt = build_review_epic_prompt(epic, run)
    session = await client.create_session(title=f"Review {epic.id} round {epic.review_round}", directory=run.repo_dir)
    epic.opencode_session_id = session["id"]

    queue = event_listener.subscribe(session["id"])
    try:
        await client.send_prompt_async(session["id"], prompt, directory=run.repo_dir)
        result_text = await _wait_for_review_completion(session["id"], queue, client)
    finally:
        event_listener.unsubscribe(session["id"], queue)

    if result_text is None:
        return None

    return parse_epic_review_result(result_text)


async def _wait_for_review_completion(session_id: str, queue: asyncio.Queue, client: OpenCodeClient) -> str | None:
    """Same dual strategy as _wait_for_step_completion: react to session.idle when
    the event feed delivers it, otherwise poll the last assistant message for
    info.time.completed. Without the fallback, reviews silently time out and
    auto-approve, so the epic review gate never actually runs. Uses the same
    completed-turn + stable-fingerprint debounce as _wait_for_step_completion so it
    does not harvest at an intermediate turn boundary."""
    poll_every = 3.0
    deadline = 600.0
    elapsed = 0.0
    QUIESCE_POLLS = 7
    last_fp: tuple | None = None
    stable = 0
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=poll_every)
        except asyncio.TimeoutError:
            event = None

        if event is not None:
            event_type = event.get("type", "")
            if event_type == "session.idle":
                return _latest_assistant_text(await client.get_messages(session_id)) or None
            if event_type == "permission.updated":
                perm_id = event.get("properties", {}).get("id", "")
                if perm_id:
                    await client.respond_permission(session_id, perm_id, "always")
            continue

        elapsed += poll_every
        try:
            msgs = await client.get_messages(session_id)
        except Exception:
            msgs = None
        if msgs:
            fp = _session_fingerprint(msgs)
            if _assistant_turn_complete(msgs) and fp == last_fp:
                stable += 1
                if stable >= QUIESCE_POLLS:
                    return _latest_assistant_text(msgs) or None
            else:
                stable = 0
            last_fp = fp
        if elapsed >= deadline:
            return None


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
    run.status = RunStatus.running
    resume = get_resume_event(run_id)
    resume.set()
    await notify_sse(run, "run_resumed", {})
    return True


async def try_resume_run(run_id: str, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> bool:
    run = get_run(run_id)
    # Resume a paused run, and also RECOVER a failed one in place: _run_loop skips
    # already-approved epics and never re-runs done steps (select_next_ready_step
    # only picks ready steps), so recovery continues from the first unfinished
    # step without redoing completed work or re-prompting passed gates.
    if not run or run.status not in (RunStatus.paused, RunStatus.failed):
        return False
    run.status = RunStatus.running
    if run_id in _active_tasks and not _active_tasks[run_id].done():
        resume = get_resume_event(run_id)
        resume.set()
    else:
        task = asyncio.create_task(_run_loop(run, client, event_listener))
        _active_tasks[run_id] = task
    await notify_sse(run, "run_resumed", {})
    return True


async def jump_to_step(run_id: str, step_id: str, epic_id: str | None = None, reset_dependents: bool = True) -> dict:
    run = get_run(run_id)
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

    run.forced_next_step = step_id
    run.current_epic_id = target_epic.id
    run.current_story_id = target_story.id
    run.current_step_id = step_id

    resume = get_resume_event(run_id)
    if run.status == RunStatus.paused:
        run.status = RunStatus.running
        resume.set()

    await notify_sse(run, "step_jumped", {"step_id": step_id, "reset_steps": reset_ids}, step_id=step_id, story_id=target_story.id, epic_id=target_epic.id)
    return {"status": "jump_scheduled", "step_id": step_id, "reset_steps": reset_ids}


async def restart_run(run_id: str, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> dict:
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


async def _relaunch_loop(run: RunState, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> None:
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


async def restart_epic(run_id: str, epic_id: str, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> dict:
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


async def restart_story(run_id: str, epic_id: str, story_id: str, client: OpenCodeClient, event_listener: OpenCodeEventListener) -> dict:
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
    # CANCEL the execution task — setting the status alone leaves a ZOMBIE: the
    # loop only re-checks status at pause points, so an "aborted" run kept
    # executing stories (LLM sessions mutating the target) concurrently with the
    # next run. Same cancel pattern as delete_run.
    task = _active_tasks.pop(run_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    run.status = RunStatus.aborted  # task teardown may have flipped it (failed/paused)
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
                step.status = StepStatus.ready
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
