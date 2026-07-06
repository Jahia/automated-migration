"""manual.py — the manual zoning inspector, integrated into the orchestrator (Julian).

Serves the per-project manual inspector pages + a decisions API + an apply action, all
under /projects/{project}/zoning/* (same-origin as /app → no CORS). This is the FastAPI
home of what orchestration/lib/manual_server.py serves standalone; the React cockpit
embeds the inspector via <iframe> and drives regen/apply from here.

  GET  /projects/{project}/zoning/pages                -> {"pages":[{slug,decisions}]}
  GET  /projects/{project}/zoning/mirror/{path}        -> serve a local-mirror file (safe-joined)
  GET  /projects/{project}/zoning/decisions[?page=]    -> {"decisions":[...]}
  POST /projects/{project}/zoning/decide  {decision}   -> upsert  -> {"decisions":[...page]}
  POST /projects/{project}/zoning/delete  {"id":...}   -> remove  -> {"decisions":[...all]}
  POST /projects/{project}/zoning/clear   {"page":...} -> clear   -> {"decisions":[]}
  POST /projects/{project}/zoning/apply                -> re-run the engine, return its summary

`project` is validated as a bare segment (no traversal, mirrors content_progress.py);
mirror paths are resolved and MUST stay under the project's local-mirror dir. Decisions
persist to projects/<project>/workflow-output/manual-decisions.json — the OVERRIDES the
deterministic engine consumes on the next run (see zone_to_contentload.apply_decision).
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

log = logging.getLogger(__name__)

router = APIRouter()


def _harness_root() -> Path:
    """The jahiaMigration repo root (src/routes/ → src/ → migration-orchestrator/ → root)."""
    return Path(__file__).resolve().parents[3]


def _valid_project(project: str) -> bool:
    """A safe project segment: non-empty, no separators, no traversal, no absolute path."""
    if not project or project in (".", ".."):
        return False
    if "/" in project or "\\" in project or "\x00" in project:
        return False
    return Path(project).name == project


def _mirror_dir(project: str) -> Path:
    return _harness_root() / "projects" / project / "workflow-output" / "local-mirror"


def _decisions_path(project: str) -> Path:
    return _harness_root() / "projects" / project / "workflow-output" / "manual-decisions.json"


def _load(project: str) -> list[dict]:
    p = _decisions_path(project)
    if p.is_file():
        try:
            return json.load(open(p, encoding="utf-8")).get("decisions", [])
        except (OSError, ValueError):
            return []
    return []


def _backup(p: Path) -> None:
    """Copy the current decisions file to a timestamped .bak BEFORE overwriting, so a
    decision can never be lost to a clobber (Julian, 2026-07-06 — after a test overwrote
    real decisions). Only backs up a NON-empty file; keeps the last 30 backups."""
    if not p.is_file():
        return
    try:
        if not json.load(open(p, encoding="utf-8")).get("decisions"):
            return  # empty → nothing worth preserving
    except (OSError, ValueError):
        return
    bdir = p.parent / "manual-decisions-backups"
    try:
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, bdir / f"manual-decisions.{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json")
        for old in sorted(bdir.glob("manual-decisions.*.json"))[:-30]:
            old.unlink()
    except OSError as e:
        log.warning(f"manual-decisions backup failed: {e}")


def _save(project: str, decisions: list[dict]) -> None:
    p = _decisions_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    _backup(p)  # snapshot the pre-write state → any clobber is recoverable
    json.dump({"project": project, "decisions": decisions},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _require(project: str) -> None:
    if not _valid_project(project):
        raise HTTPException(status_code=400, detail="invalid project name")


@router.get("/zoning/projects")
async def zoning_projects() -> dict:
    """Projects that have generated manual inspector pages (a local-mirror with *.manual.html)."""
    root = _harness_root() / "projects"
    out: list[dict] = []
    if root.is_dir():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            md = d / "workflow-output" / "local-mirror"
            if md.is_dir():
                n = len(list(md.glob("*.manual.html")))
                if n:
                    out.append({"project": d.name, "pages": n})
    return {"projects": out}


@router.get("/projects/{project}/zoning/pages")
async def zoning_pages(project: str) -> dict:
    """List the slugs that have a generated <slug>.manual.html, with their decision count."""
    _require(project)
    md = _mirror_dir(project)
    if not md.is_dir():
        raise HTTPException(status_code=404, detail=f"no local-mirror for project: {project}")
    counts: dict[str, int] = {}
    for d in _load(project):
        counts[d.get("page")] = counts.get(d.get("page"), 0) + 1
    slugs = sorted(f.name[: -len(".manual.html")] for f in md.glob("*.manual.html"))
    return {"project": project,
            "pages": [{"slug": s, "decisions": counts.get(s, 0)} for s in slugs]}


@router.get("/projects/{project}/zoning/mirror/{path:path}")
async def zoning_mirror(project: str, path: str):
    """Serve a file from the project's local-mirror (the <slug>.manual.html and its
    relative assets/). Resolved path MUST stay under the mirror dir."""
    _require(project)
    md = _mirror_dir(project).resolve()
    if not md.is_dir():
        raise HTTPException(status_code=404, detail="no local-mirror")
    target = (md / path).resolve()
    try:
        target.relative_to(md)  # traversal guard: target must be under the mirror
    except ValueError:
        raise HTTPException(status_code=403, detail="path escapes mirror")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(target))


@router.get("/projects/{project}/zoning/decisions")
async def zoning_decisions(project: str, page: str | None = None) -> dict:
    _require(project)
    ds = _load(project)
    if page:
        ds = [d for d in ds if d.get("page") == page]
    return {"decisions": ds}


@router.post("/projects/{project}/zoning/decide")
async def zoning_decide(project: str, request: Request) -> dict:
    """Upsert a decision (dedup by deterministic id page|selector)."""
    _require(project)
    body = await request.json()
    d = body.get("decision") or body
    if not d.get("id"):
        d["id"] = f"{d.get('page', '')}|{(d.get('selector') or {}).get('value', '')}"
    ds = [x for x in _load(project) if x.get("id") != d["id"]] + [d]
    _save(project, ds)
    return {"decisions": [x for x in ds if x.get("page") == d.get("page")]}


@router.post("/projects/{project}/zoning/delete")
async def zoning_delete(project: str, request: Request) -> dict:
    _require(project)
    body = await request.json()
    ds = [x for x in _load(project) if x.get("id") != body.get("id")]
    _save(project, ds)
    return {"decisions": ds}


@router.post("/projects/{project}/zoning/clear")
async def zoning_clear(project: str, request: Request) -> dict:
    _require(project)
    body = await request.json()
    pg = body.get("page")
    ds = [x for x in _load(project) if x.get("page") != pg]
    _save(project, ds)
    return {"decisions": []}


@router.post("/projects/{project}/zoning/apply")
async def zoning_apply(project: str) -> dict:
    """Re-run the deterministic engine so the manual decisions land in the content-load.
    Runs under system python3 (the orchestrator venv lacks bs4; pipeline scripts always
    run under python3 — same convention as the plan steps). Returns the engine summary."""
    _require(project)
    if not _mirror_dir(project).is_dir():
        raise HTTPException(status_code=404, detail=f"no local-mirror for project: {project}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", "orchestration/lib/zone_to_contentload.py", project,
            cwd=str(_harness_root()),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="engine apply timed out")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"could not run engine: {e}")
    lines = (out or b"").decode("utf-8", "replace").splitlines()
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "head": next((ln.strip() for ln in lines if ln.startswith(project + ":")), None),
        "summary": next((ln.strip() for ln in lines if "MANUAL decisions applied" in ln), None),
        "tail": lines[-1].strip() if lines else "",
    }
