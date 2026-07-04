from __future__ import annotations

import asyncio
import logging
import re
import time

from .models import (
    EpicInput,
    EpicState,
    EpicStatus,
    PlanInput,
    RunState,
    RunStatus,
    StepInput,
    StepState,
    StepStatus,
    StepTransition,
    StoryInput,
    StoryState,
    StoryStatus,
    TraceEvent,
)
from .verifier import PROBE_RE

log = logging.getLogger(__name__)

# Steps whose id/title matches this MUST carry >=1 engine-enforced PROBE — a
# deploy/content/publish/scaffold step that auto-passes on the agent's
# self-report is exactly the gate-integrity hole P0.3 closes.
GATED_STEP_RE = re.compile(r"deploy|content|publish|scaffold", re.IGNORECASE)


class PlanLintError(ValueError):
    pass


def _has_probe(step_input: StepInput) -> bool:
    return any(PROBE_RE.match(c) for c in step_input.acceptance_criteria or [])


def probe_lines(criteria: list[str] | None) -> list[str]:
    return [c for c in (criteria or []) if PROBE_RE.match(c)]


def lint_plan(plan: PlanInput) -> None:
    """Plan-load gate:
    - deploy/content/publish/scaffold steps without a PROBE fail creation
      (review:true steps are exempt — the engine never sends them to an agent);
    - any other PROBE-less step is only warned (it will auto-pass on the
      agent's self-report);
    - strategy patches must PRESERVE every PROBE: line of the target step
      verbatim (additions allowed) unless the strategy is a generator-emitted
      arm_swap — frozen bars live in probe code, patches never touch them."""
    offenders: list[str] = []
    unprobed: list[str] = []
    strategy_offenders: list[str] = []
    steps_by_id: dict[str, StepInput] = {
        step.id: step for epic in plan.epics for story in epic.stories for step in story.steps
    }
    for epic in plan.epics:
        for story in epic.stories:
            for step in story.steps:
                for strat in step.strategies or []:
                    for patch in strat.patches:
                        target = steps_by_id.get(patch.step_id)
                        if target is None:
                            strategy_offenders.append(
                                f"{step.id}/{strat.id}: patch targets unknown step '{patch.step_id}'")
                            continue
                        if strat.arm_swap or patch.acceptance_criteria is None:
                            continue
                        missing = [p for p in probe_lines(target.acceptance_criteria)
                                   if p not in patch.acceptance_criteria]
                        if missing:
                            strategy_offenders.append(
                                f"{step.id}/{strat.id} → {patch.step_id}: PROBE line(s) removed or "
                                f"modified (arm_swap=false forbids it): {'; '.join(m[:120] for m in missing)}")
                if _has_probe(step) or step.review:
                    continue
                if GATED_STEP_RE.search(step.id) or GATED_STEP_RE.search(step.title):
                    offenders.append(f"{epic.id}/{story.id}/{step.id} ({step.title})")
                else:
                    unprobed.append(step.id)
    if strategy_offenders:
        raise PlanLintError(
            "plan lint: non-arm_swap strategy patches must preserve every PROBE: line of the "
            "target step verbatim — " + "; ".join(strategy_offenders)
        )
    if offenders:
        raise PlanLintError(
            "plan lint: deploy/content/publish/scaffold steps must carry at least one "
            "'PROBE:' line in acceptance_criteria — offending steps: " + "; ".join(offenders)
        )
    if unprobed:
        log.warning(f"plan lint: steps with zero PROBE lines (verified only by agent self-report): {', '.join(unprobed)}")


def build_step_state(step_input: StepInput, story_id: str) -> StepState:
    return StepState(
        id=step_input.id,
        story_id=story_id,
        title=step_input.title,
        task_type=step_input.task_type,
        agent=step_input.agent or "code",
        depends_on=step_input.depends_on,
        inputs=step_input.inputs,
        expected_outputs=step_input.expected_outputs,
        acceptance_criteria=step_input.acceptance_criteria,
        max_attempts=step_input.max_attempts,
        strategies=step_input.strategies,
        review=step_input.review,
    )


def build_story_state(story_input: StoryInput) -> StoryState:
    steps = [build_step_state(s, story_input.id) for s in story_input.steps]
    return StoryState(
        id=story_input.id,
        title=story_input.title,
        description=story_input.description,
        acceptance_criteria=story_input.acceptance_criteria,
        depends_on=story_input.depends_on,
        github_issues=story_input.github_issues,
        steps=steps,
    )


def build_epic_state(epic_input: EpicInput) -> EpicState:
    return EpicState(
        id=epic_input.id,
        title=epic_input.title,
        goal=epic_input.goal,
        github_issues=epic_input.github_issues,
        stories=[build_story_state(s) for s in epic_input.stories],
        review_config=epic_input.review_config,
    )


def build_run_state(plan: PlanInput) -> RunState:
    lint_plan(plan)
    now = time.time() * 1000
    return RunState(
        run_id=f"run_{int(now)}",
        goal=plan.goal,
        repo_dir=plan.repo_dir,
        github_repo=plan.github_repo,
        model=plan.model,
        epics=[build_epic_state(e) for e in plan.epics],
        created_at=now,
        updated_at=now,
    )


def select_next_ready_story(epic: EpicState) -> StoryState | None:
    for story in epic.stories:
        if story.status != StoryStatus.pending:
            continue
        if all_story_deps_done(epic, story):
            return story
    return None


def all_story_deps_done(epic: EpicState, story: StoryState) -> bool:
    for dep_id in story.depends_on:
        dep = get_story_by_id(epic, dep_id)
        if dep and dep.status != StoryStatus.approved:
            return False
    return True


def all_stories_approved(epic: EpicState) -> bool:
    return all(s.status == StoryStatus.approved for s in epic.stories)


def all_steps_done(story: StoryState) -> bool:
    return all(s.status == StepStatus.done for s in story.steps)


def get_story_by_id(epic: EpicState, story_id: str) -> StoryState | None:
    for s in epic.stories:
        if s.id == story_id:
            return s
    return None


def get_step_by_id(story: StoryState, step_id: str) -> StepState | None:
    for s in story.steps:
        if s.id == step_id:
            return s
    return None


def get_epic_by_id(run: RunState, epic_id: str) -> EpicState | None:
    for e in run.epics:
        if e.id == epic_id:
            return e
    return None


def select_next_ready_step(story: StoryState) -> StepState | None:
    for step in story.steps:
        if step.status != StepStatus.pending:
            continue
        if all_step_deps_done(story, step):
            return step
    return None


def all_step_deps_done(story: StoryState, step: StepState) -> bool:
    for dep_id in step.depends_on:
        dep = get_step_by_id(story, dep_id)
        if dep and dep.status != StepStatus.done:
            return False
    return True


def check_transition(step: StepState, story: StoryState) -> StepTransition | None:
    if step.agent_result and step.agent_result.status == "failed" and step.agent_result.loop_to:
        target = get_step_by_id(story, step.agent_result.loop_to)
        if target:
            return StepTransition(from_step_id=step.id, to_step_id=target.id)
    return None


def reset_steps_from(story: StoryState, from_step_id: str) -> list[str]:
    found = False
    reset_ids = []
    for step in story.steps:
        if step.id == from_step_id:
            found = True
        if found:
            step.status = StepStatus.pending
            step.agent_result = None
            step.verification = None
            step.streaming_text = ""
            step.attempt = 0
            reset_ids.append(step.id)
    return reset_ids


# ── Gate decisions (halted → done|rejected) ───────────────────────────
# A halted step is a human gate. It is decided ONLY by the typed gate endpoint
# (approve/reject) or redone via jump — a plain resume never decides it.


def find_halted_step(run: RunState) -> tuple[EpicState, StoryState, StepState] | tuple[None, None, None]:
    for epic in run.epics:
        for story in epic.stories:
            for step in story.steps:
                if step.status == StepStatus.halted:
                    return epic, story, step
    return None, None, None


def gate_blocked_step(run: RunState) -> StepState | None:
    """The step (if any) that blocks a plain resume: a halted gate awaiting an
    approve/reject decision, a rejected gate awaiting jump/rollback, or a
    decision_pending step awaiting POST /decide."""
    for epic in run.epics:
        for story in epic.stories:
            for step in story.steps:
                if step.status in (StepStatus.halted, StepStatus.rejected, StepStatus.decision_pending):
                    return step
    return None


def find_decision_steps(run: RunState) -> list[tuple[EpicState, StoryState, StepState]]:
    return [(epic, story, step)
            for epic in run.epics
            for story in epic.stories
            for step in story.steps
            if step.status == StepStatus.decision_pending]


def approve_gate_step(step: StepState) -> bool:
    if step.status != StepStatus.halted:
        return False
    step.status = StepStatus.done
    return True


def reject_gate_step(step: StepState) -> bool:
    if step.status != StepStatus.halted:
        return False
    step.status = StepStatus.rejected
    return True


def normalize_for_resume(run: RunState) -> None:
    """Fresh-loop recovery (engine restarted / loop gone): the in-flight resume
    handling can't fire, so normalize state or the loop dies instantly —
      - orphaned running/verifying step (loop died mid-step): re-run it;
      - failed step: give it fresh attempts;
      - failed story/epic with runnable work left: back to pending so
        select_next_ready_* re-enters instead of re-failing immediately.
    Halted, rejected AND decision_pending steps are left UNTOUCHED — resume
    never decides a gate or a decision point (gate_blocked_step refuses the
    resume outright while one exists)."""
    for epic in run.epics:
        for story in epic.stories:
            for step in story.steps:
                if step.status in (StepStatus.running, StepStatus.verifying, StepStatus.ready, StepStatus.failed):
                    # back to *pending*: despite its name, select_next_ready_step
                    # only picks pending steps ('ready' is jump's forced state)
                    step.status = StepStatus.pending
                    step.attempt = 0
            if story.status == StoryStatus.running:
                # persisted mid-story (halt/crash): the old loop is gone and
                # select_next_ready_story only picks pending — left as running,
                # the fresh loop finds no story, fails the epic, fails the run
                story.status = StoryStatus.pending
            elif story.status == StoryStatus.failed and any(
                    s.status == StepStatus.pending for s in story.steps):
                story.status = StoryStatus.pending
        if epic.status in (EpicStatus.running, EpicStatus.failed) and any(
                st.status != StoryStatus.approved for st in epic.stories):
            epic.status = EpicStatus.pending
        elif epic.status == EpicStatus.failed:
            # Failed at the REVIEW stage (every story approved): re-enter the
            # epic so the review re-runs. With overrule semantics a rejected
            # proposal now approves the epic, so this branch only recovers
            # legacy state (pre-overrule rejections) or a reviewer crash.
            epic.status = EpicStatus.pending


def find_all_dependents(story: StoryState, step_id: str) -> set[str]:
    dependents: set[str] = set()
    queue = [step_id]
    while queue:
        current = queue.pop()
        for step in story.steps:
            if current in step.depends_on and step.id not in dependents:
                dependents.add(step.id)
                queue.append(step.id)
    return dependents


def make_trace_event(
    event_type: str,
    run: RunState,
    *,
    step_id: str | None = None,
    story_id: str | None = None,
    epic_id: str | None = None,
    payload: dict | None = None,
) -> TraceEvent:
    return TraceEvent(
        seq=len(run.trace) + 1,
        timestamp=time.time() * 1000,
        type=event_type,
        step_id=step_id,
        story_id=story_id,
        epic_id=epic_id,
        payload=payload or {},
    )


_resume_events: dict[str, asyncio.Event] = {}


def get_resume_event(run_id: str) -> asyncio.Event:
    if run_id not in _resume_events:
        _resume_events[run_id] = asyncio.Event()
        _resume_events[run_id].set()
    return _resume_events[run_id]
