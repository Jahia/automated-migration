from __future__ import annotations

import asyncio
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
