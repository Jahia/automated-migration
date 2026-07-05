from __future__ import annotations

from fastapi import APIRouter, Request

from ..orchestrator import (
    get_run,
    restart_epic,
    restart_story,
)
from ..state import get_epic_by_id

router = APIRouter()


@router.get("/runs/{run_id}/epics")
async def list_epics(run_id: str):
    run = get_run(run_id)
    if not run:
        return {"error": "run not found"}
    return [
        {
            "id": epic.id,
            "title": epic.title,
            "goal": epic.goal,
            "status": epic.status.value,
            "review_round": epic.review_round,
            "stories_count": len(epic.stories),
            # pending_proposal is a compat-read field (P5.5b removed the LLM reviewer);
            # the engine never sets it now, so it is always null for new runs.
            "pending_proposal": epic.pending_proposal.model_dump() if epic.pending_proposal else None,
        }
        for epic in run.epics
    ]


@router.get("/runs/{run_id}/epics/{epic_id}")
async def get_epic_detail(run_id: str, epic_id: str):
    run = get_run(run_id)
    if not run:
        return {"error": "run not found"}
    epic = get_epic_by_id(run, epic_id)
    if not epic:
        return {"error": "epic not found"}
    return epic.model_dump()


# P5.5b: the /proposal/approve and /proposal/reject endpoints were removed with the
# LLM epic reviewer (epic approval is now deterministic in the orchestrator).


@router.post("/runs/{run_id}/epics/{epic_id}/restart")
async def restart_epic_endpoint(run_id: str, epic_id: str, request: Request):
    """Reset this epic (and all its stories/steps) to pending and re-run it.
    Earlier approved epics are skipped; later epics stay pending."""
    return await restart_epic(
        run_id, epic_id,
        request.app.state.llm_client,
        request.app.state.event_listener,
    )


@router.post("/runs/{run_id}/epics/{epic_id}/stories/{story_id}/restart")
async def restart_story_endpoint(run_id: str, epic_id: str, story_id: str, request: Request):
    """Reset this story (and its dependents) to pending and re-run it. The parent
    epic is re-opened so the loop re-enters and re-reviews; approved sibling
    stories stay approved."""
    return await restart_story(
        run_id, epic_id, story_id,
        request.app.state.llm_client,
        request.app.state.event_listener,
    )
