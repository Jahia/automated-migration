from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from ..github_client import GitHubClient
from ..models import PlanInput, RunState, RunStatus
from ..opencode_client import OpenCodeClient
from ..opencode_events import OpenCodeEventListener
from ..orchestrator import (
    abort_run,
    delete_run,
    get_run,
    jump_to_step,
    pause_run,
    prune_runs,
    register_run,
    restart_run,
    resume_run,
    start_run,
    try_resume_run,
)
from ..persistence import list_runs, load_run, save_run
from ..state import build_run_state

log = logging.getLogger(__name__)

router = APIRouter()


class RunResponse(BaseModel):
    run_id: str
    status: str
    message: str = ""


class JumpRequest(BaseModel):
    step_id: str
    epic_id: str | None = None
    reset_dependents: bool = True


@router.post("/runs", response_model=RunResponse)
async def create_run(plan: PlanInput, request: Request):
    github: GitHubClient = request.app.state.github_client

    run = build_run_state(plan)
    run.status = RunStatus.created

    for epic_input, epic_state in zip(plan.epics, run.epics):
        epic_state.github_issues_content = await github.fetch_issues(epic_input.github_issues, plan.github_repo)
        for story_input, story_state in zip(epic_input.stories, epic_state.stories):
            story_state.github_issues_content = await github.fetch_issues(story_input.github_issues, plan.github_repo)

    register_run(run)
    await save_run(run)
    return RunResponse(run_id=run.run_id, status="created", message="Run créé. POST /runs/{run_id}/start pour démarrer.")


@router.post("/runs/{run_id}/start", response_model=RunResponse)
async def start_run_endpoint(run_id: str, request: Request, background_tasks: BackgroundTasks):
    run = get_run(run_id)
    if not run:
        run = await load_run(run_id)
    if not run:
        return RunResponse(run_id=run_id, status="error", message="Run non trouvé")
    if run.status != RunStatus.created:
        return RunResponse(run_id=run_id, status=run.status.value, message=f"Le run est déjà en statut {run.status.value}")

    client: OpenCodeClient = request.app.state.opencode_client
    event_listener: OpenCodeEventListener = request.app.state.event_listener

    run.status = RunStatus.running
    await save_run(run)
    background_tasks.add_task(start_run, run, client, event_listener)
    return RunResponse(run_id=run.run_id, status="running", message="Run démarré")


@router.get("/runs")
async def get_runs():
    return await list_runs()


@router.get("/runs/{run_id}")
async def get_run_detail(run_id: str):
    run = get_run(run_id)
    if not run:
        run = await load_run(run_id)
        if run:
            register_run(run)
    if not run:
        return {"error": "run not found"}
    return run.model_dump()


@router.post("/runs/{run_id}/pause")
async def pause_run_endpoint(run_id: str):
    ok = await pause_run(run_id)
    return {"status": "paused" if ok else "error"}


@router.post("/runs/{run_id}/resume")
async def resume_run_endpoint(run_id: str, request: Request):
    run = get_run(run_id)
    if not run:
        run = await load_run(run_id)
        if run:
            register_run(run)
    client: OpenCodeClient = request.app.state.opencode_client
    event_listener: OpenCodeEventListener = request.app.state.event_listener
    ok = await try_resume_run(run_id, client, event_listener)
    return {"status": "resumed" if ok else "error"}


@router.post("/runs/{run_id}/jump")
async def jump_endpoint(run_id: str, req: JumpRequest):
    result = await jump_to_step(run_id, req.step_id, req.epic_id, req.reset_dependents)
    return result


@router.post("/runs/{run_id}/abort")
async def abort_endpoint(run_id: str):
    ok = await abort_run(run_id)
    return {"status": "aborted" if ok else "error"}


@router.post("/runs/prune")
async def prune_runs_endpoint():
    """Delete all finished runs (completed/failed/aborted). Active runs are kept."""
    deleted = await prune_runs()
    return {"deleted": deleted, "count": len(deleted)}


@router.delete("/runs/{run_id}", response_model=RunResponse)
async def delete_run_endpoint(run_id: str):
    ok = await delete_run(run_id)
    return RunResponse(
        run_id=run_id,
        status="deleted" if ok else "error",
        message="Run supprimé" if ok else "Run non trouvé",
    )


@router.post("/runs/{run_id}/restart", response_model=RunResponse)
async def restart_run_endpoint(run_id: str, request: Request):
    client: OpenCodeClient = request.app.state.opencode_client
    event_listener: OpenCodeEventListener = request.app.state.event_listener
    result = await restart_run(run_id, client, event_listener)
    if "error" in result:
        return RunResponse(run_id=run_id, status="error", message=result["error"])
    return RunResponse(run_id=run_id, status="running", message="Run relancé")
