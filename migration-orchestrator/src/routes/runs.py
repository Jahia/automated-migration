from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..github_client import GitHubClient
from ..migration_control import compact_status, log_tail, project_path, quality_verdict, workflow_output_dir
from ..models import EpicInput, PlanInput, RunState, RunStatus, StepInput, StoryInput
from ..opencode_client import OpenCodeClient
from ..opencode_events import OpenCodeEventListener
from ..orchestrator import (
    abort_run,
    approve_gate,
    decide_step,
    decision_bundles,
    delete_run,
    get_run,
    jump_to_step,
    pause_run,
    prune_runs,
    register_run,
    reject_gate,
    restart_run,
    resume_run,
    start_run,
    try_resume_run,
)
from ..persistence import list_runs, load_run, save_event, save_run
from ..state import PlanLintError, build_run_state

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

    try:
        run = build_run_state(plan)
    except PlanLintError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    """Run list with live-truth status: in-memory beats the persisted column, and a
    persisted 'running' with no active loop means the engine restarted → 'paused'
    (same normalization load_run applies to the state blob)."""
    rows = await list_runs()
    for r in rows:
        mem = get_run(r["run_id"])
        if mem:
            r["status"] = mem.status.value
        elif r["status"] == "running":
            r["status"] = "paused"
    return rows


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
async def jump_endpoint(run_id: str, req: JumpRequest, request: Request):
    result = await jump_to_step(
        run_id, req.step_id, req.epic_id, req.reset_dependents,
        client=request.app.state.opencode_client,
        event_listener=request.app.state.event_listener,
    )
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


# ── Migration profile: domain artifacts + fidelity actions ───────────

def _project_path(run: RunState) -> str | None:
    """The project dir this run migrates (from any step's inputs)."""
    for epic in run.epics:
        for story in epic.stories:
            for step in story.steps:
                pp = step.inputs.get("project_path") or step.inputs.get("project")
                if pp:
                    return str(pp)
    return None


async def _resolve_run(run_id: str) -> RunState:
    run = get_run(run_id)
    if not run:
        run = await load_run(run_id)
        if run:
            register_run(run)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/runs/{run_id}/artifacts/{path:path}")
async def get_artifact(run_id: str, path: str):
    """Serve a file from the run's project workflow-output (screenshots, JSON, CND)."""
    run = await _resolve_run(run_id)
    proj = _project_path(run)
    if not proj:
        raise HTTPException(status_code=404, detail="no project for run")
    base = (Path(run.repo_dir) / proj / "workflow-output").resolve()
    target = (base / path).resolve()
    if base != target and not str(target).startswith(str(base) + "/"):
        raise HTTPException(status_code=403, detail="path traversal blocked")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(target))


class FidelityRerun(BaseModel):
    pages: list[str] = []


@router.post("/runs/{run_id}/fidelity/rerun")
async def fidelity_rerun(run_id: str, req: FidelityRerun):
    """Re-run the reconstruction probe on a chosen page sample (fire-and-forget)."""
    run = await _resolve_run(run_id)
    proj = _project_path(run)
    if not proj:
        raise HTTPException(status_code=404, detail="no project for run")
    args = ["node", "orchestration/lib/reconstruct_probe.mjs", proj, "95"]
    if req.pages:
        args += ["--pages", ",".join(req.pages)]
    subprocess.Popen(args, cwd=run.repo_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "rerunning", "pages": req.pages}


# ── Migration profile: create a run from the fixed analyze plan ───────
#
# The generic engine takes an arbitrary Epic/Story/Step plan (POST /runs).
# A migration is that plan *held fixed* (the deterministic analyze pipeline:
# crawl → semantic_extract → group_llm(DeepSeek) → assemble+CND → fidelity gate)
# and parameterized by a handful of site facts. The NewMigration cockpit form
# posts those facts here; we materialize the plan and register the run.


class MigrationInput(BaseModel):
    site_url: str
    project: str
    ns: str
    mixns: str | None = None
    max_pages: int = 18
    depth: int = 2
    rate_delay: int = 2
    sample_pages: list[str] = []
    repo_dir: str | None = None
    autonomy: str = "assisted"        # manual | assisted | autonomous (see CONTROL-LOOP.md)


def _harness_root() -> str:
    """The jahiaMigration repo root (where AGENTS.md + orchestration/ live)."""
    return str(Path(__file__).resolve().parents[3])


def _build_migration_plan(inp: MigrationInput) -> PlanInput:
    """The fixed analyze plan, parameterized. Mirrors
    orchestration/plans/acquia-analyze.plan.json step-for-step so a run created
    here executes identically to the reference deterministic pipeline."""
    proj = inp.project
    ns = inp.ns
    mixns = inp.mixns or f"{ns}mix"
    repo_dir = inp.repo_dir or _harness_root()
    pp = f"projects/{proj}"
    wo = f"{pp}/workflow-output"
    # gate sample size: up to 10 pages — one per template cluster first (diverse
    # layouts, see clusterSample in mirror_net.mjs), then leftover budget filled from
    # the biggest clusters. Capped by the crawl. Pass --all to the probe to verify
    # every crawled page instead of a sample.
    recon_max = min(10, inp.max_pages)
    pages_flag = f" --pages {','.join(inp.sample_pages)}" if inp.sample_pages else ""
    ins = {"project_path": pp, "project": proj}

    steps = [
        StepInput(
            id="step_crawl",
            title="Crawl + inventory (cache-first)",
            inputs={**ins, "site_url": inp.site_url},
            acceptance_criteria=[
                f"Run: python3 orchestration/lib/crawl-site.py {pp} {inp.site_url} "
                f"--max-pages {inp.max_pages} --depth {inp.depth} --rate-delay {inp.rate_delay} --max-asset-size 1",
                f"PROBE: test -s {wo}/page-inventory.json",
            ],
        ),
        StepInput(
            id="step_localize",
            title="Localize assets → self-contained local mirror (truly offline render)",
            depends_on=["step_crawl"],
            inputs=ins,
            acceptance_criteria=[
                f"Run: python3 orchestration/lib/localize_site.py {pp} --max-asset-size 15",
                f"PROBE: test -s {wo}/local-mirror/mirror.json",
                f"PROBE: node orchestration/lib/mirror_probe.mjs {pp} {recon_max}{pages_flag}",
            ],
        ),
        StepInput(
            id="step_semantic",
            title="Deterministic candidate extraction",
            depends_on=["step_crawl"],
            inputs=ins,
            acceptance_criteria=[
                f"Run: python3 orchestration/lib/semantic_extract.py {pp}",
                f"PROBE: test -s {wo}/semantic-candidates.json",
                f"PROBE: python3 -c \"import json;d=json.load(open('{wo}/semantic-candidates.json'));"
                f"assert len(d['crossCutting'])>=1 and len(d['components'])>=1\"",
            ],
        ),
        StepInput(
            id="step_group",
            title="Bounded LLM grouping via DeepSeek V4 Flash (self-correcting, gate-clean)",
            depends_on=["step_semantic"],
            inputs=ins,
            acceptance_criteria=[
                f"Run: python3 orchestration/lib/group_llm.py {pp} --model deepseek-v4-flash "
                f"--ns {ns} --out {wo}/grouping.json --retries 4",
                f"PROBE: python3 orchestration/lib/assemble_manifest.py {wo}/semantic-candidates.json "
                f"--group {wo}/grouping.json --ns {ns} --out {wo}/component-manifest.json",
            ],
        ),
        StepInput(
            id="step_cnd",
            title="Emit CND + view plan (deterministic)",
            depends_on=["step_group"],
            inputs=ins,
            acceptance_criteria=[
                f"Run: python3 orchestration/lib/cnd_emit.py {wo}/component-manifest.json "
                f"--ns {ns} --mixns {mixns} --project {proj} "
                f"--out-cnd {wo}/definitions.cnd --out-views {wo}/views.json",
                f"PROBE: test -s {wo}/definitions.cnd",
                f'PROBE: grep -q "{ns} = " {wo}/definitions.cnd',
                f"PROBE: test -s {wo}/views.json",
            ],
        ),
        StepInput(
            id="step_reconstruct_gate",
            title="Round-trip fidelity gate: reconstruct sample pages and pixel-diff vs source (BEFORE templatization)",
            depends_on=["step_cnd", "step_localize"],
            inputs=ins,
            acceptance_criteria=[
                "Reconstructs the sample pages from ONLY the extracted component nodes, renders in a "
                "real browser, pixel-diffs against the live source, and writes a self-contained visual "
                "review at workflow-output/reconstruct/review.html. GATE = content coverage.",
                f"PROBE: node orchestration/lib/reconstruct_probe.mjs {pp} {recon_max} 95{pages_flag}",
                'After the PROBE passes, return status: "halt" so the operator can review the '
                "fidelity gate in the cockpit before templatization.",
            ],
        ),
    ]

    epic = EpicInput(
        id="epic_analyze",
        title="Deterministic analyze",
        goal="Crawl, extract candidates deterministically, group via DeepSeek (gate-verified), "
        "assemble manifest + CND, then verify with the round-trip fidelity gate.",
        stories=[StoryInput(id="story_analyze", title="Analyze",
                            description="Deterministic analyze pipeline for " + inp.site_url,
                            steps=steps)],
    )
    return PlanInput(
        goal=f"Analyze {inp.site_url} into a stable Jahia component + template model "
        f"(project {proj}, namespace {ns}), CND-ready.",
        repo_dir=repo_dir,
        model="deepseek/deepseek-v4-flash",
        epics=[epic],
    )


@router.post("/migrations", response_model=RunResponse)
async def create_migration(inp: MigrationInput):
    """Create a run from the fixed deterministic analyze plan. No GitHub issues."""
    plan = _build_migration_plan(inp)
    try:
        run = build_run_state(plan)
    except PlanLintError as e:
        raise HTTPException(status_code=400, detail=str(e))
    run.status = RunStatus.created
    run.autonomy = inp.autonomy
    register_run(run)
    await save_run(run)
    return RunResponse(
        run_id=run.run_id,
        status="created",
        message="Migration créée. POST /runs/{run_id}/start pour lancer l'analyse.",
    )


# ── Agent control surface (LLM-driven piloting) — see CONTROL-LOOP.md ─
#
# Thin, decision-oriented projection over the existing engine so an LLM can drive
# a migration: poll a compact status + quality verdict, tail the log, then act
# through a typed, audited gate/rollback decision.


@router.get("/runs/{run_id}/status")
async def run_status(run_id: str):
    """Compact status: phase, current step, active gate, quality verdict, cost,
    progress, and the available next actions. The agent's cheap poll target."""
    run = await _resolve_run(run_id)
    return compact_status(run, workflow_output_dir(run))


@router.get("/runs/{run_id}/quality")
async def run_quality(run_id: str):
    """The green/amber/red quality verdict alone (for the active gate)."""
    run = await _resolve_run(run_id)
    gate = next((s for e in run.epics for st in e.stories for s in st.steps
                 if s.status.value in ("halted", "waiting_human") and s.gate_type), None)
    return quality_verdict(run, gate.gate_type if gate else None, workflow_output_dir(run))


@router.get("/runs/{run_id}/log")
async def run_log(run_id: str, since: float = 0.0, limit: int = 50):
    """Poll-friendly log tail: recent events (ts > since), active streaming, errors."""
    run = await _resolve_run(run_id)
    return log_tail(run, since, limit)


class GateDecision(BaseModel):
    decision: str            # approve | reject | rerun
    reason: str = ""
    pages: list[str] = []    # rerun: optional page sample


@router.post("/runs/{run_id}/gate")
async def run_gate(run_id: str, req: GateDecision, request: Request):
    """Typed, audited gate decision — the ONLY way to decide a halted gate.
    approve → the halted step becomes done and the run resumes; reject → the step
    becomes 'rejected' (persisted; the run stays paused until jump/rollback);
    rerun → re-run the fidelity probe on a sample."""
    run = await _resolve_run(run_id)
    dec = req.decision.lower().strip()
    await save_event(run_id, "gate_decision", {"decision": dec, "reason": req.reason, "pages": req.pages})

    if dec == "approve":
        client: OpenCodeClient = request.app.state.opencode_client
        event_listener: OpenCodeEventListener = request.app.state.event_listener
        result = await approve_gate(run_id, client, event_listener)
        if result.get("error"):
            return {"status": "error", "decision": dec, "detail": result["error"]}
        return {"status": "approved", "decision": dec, "step_id": result["step_id"]}
    if dec == "reject":
        result = await reject_gate(run_id, req.reason)
        if result.get("error"):
            return {"status": "error", "decision": dec, "detail": result["error"]}
        return {"status": "rejected", "decision": dec, "reason": req.reason, "step_id": result["step_id"]}
    if dec == "rerun":
        proj = project_path(run)
        if not proj:
            raise HTTPException(status_code=404, detail="no project for run")
        args = ["node", "orchestration/lib/reconstruct_probe.mjs", proj, "95"]
        if req.pages:
            args += ["--pages", ",".join(req.pages)]
        subprocess.Popen(args, cwd=run.repo_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"status": "rerunning", "decision": dec, "pages": req.pages}
    raise HTTPException(status_code=400, detail="decision must be approve|reject|rerun")


class DecideRequest(BaseModel):
    """POST /runs/{id}/steps/{id}/decide — decide a decision_pending step.
    strategy_id: apply a pre-registered strategy (patches/skips/halt);
    rules: scope rules appended (deduped by id) to rules_file (default derived
    from the step's projects/<name> input → workflow-output/scope-rules.json);
    patch: free-form step patch — autonomy=manual ONLY;
    action: apply_and_rerun (reset via jump machinery) | proceed (review steps)."""
    strategy_id: str | None = None
    rules: list[dict] | None = None
    rules_file: str | None = None
    patch: dict | None = None
    action: str
    rerun_from: str | None = None
    rationale: str


@router.get("/runs/{run_id}/decisions")
async def run_decisions(run_id: str):
    """Pending decision bundles: step identity, attempts, strategies
    remaining/applied, last verification + probe stdout/stderr tails, inputs —
    everything the strategist needs to pick a strategy or emit scope rules."""
    run = await _resolve_run(run_id)
    return {"run_id": run_id, "autonomy": getattr(run, "autonomy", "assisted"),
            "decisions": decision_bundles(run)}


@router.post("/runs/{run_id}/steps/{step_id}/decide")
async def run_decide(run_id: str, step_id: str, req: DecideRequest, request: Request):
    """Typed, audited decision — the ONLY way to move a step out of
    decision_pending (a plain resume is refused while one exists)."""
    await _resolve_run(run_id)
    result = await decide_step(
        run_id, step_id,
        action=req.action,
        rationale=req.rationale,
        strategy_id=req.strategy_id,
        rules=req.rules,
        rules_file=req.rules_file,
        patch=req.patch,
        rerun_from=req.rerun_from,
        client=request.app.state.opencode_client,
        event_listener=request.app.state.event_listener,
    )
    if result.get("error"):
        raise HTTPException(status_code=result.get("code", 400), detail=result["error"])
    return result


class Rollback(BaseModel):
    to_step: str
    reason: str = ""


@router.post("/runs/{run_id}/rollback")
async def run_rollback(run_id: str, req: Rollback, request: Request):
    """Roll the run back to an earlier step (re-runs it, resets dependents). Audited."""
    run = await _resolve_run(run_id)
    await save_event(run_id, "rollback", {"to_step": req.to_step, "reason": req.reason})
    result = await jump_to_step(
        run_id, req.to_step, None, True,
        client=request.app.state.opencode_client,
        event_listener=request.app.state.event_listener,
    )
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "rolled_back", "to_step": req.to_step, "result": result}
