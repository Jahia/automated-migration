from __future__ import annotations

from fastapi import APIRouter, Request

from ..orchestrator import (
    approve_proposal,
    get_run,
    reject_proposal,
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


@router.post("/runs/{run_id}/epics/{epic_id}/proposal/approve")
async def approve_epic_proposal(run_id: str, epic_id: str):
    ok = await approve_proposal(run_id, epic_id)
    return {"status": "approved" if ok else "error"}


@router.post("/runs/{run_id}/epics/{epic_id}/proposal/reject")
async def reject_epic_proposal(run_id: str, epic_id: str):
    ok = await reject_proposal(run_id, epic_id)
    return {"status": "rejected" if ok else "error"}


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
