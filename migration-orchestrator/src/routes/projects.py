"""projects.py — project-level grouping over runs (P1).

"Project" is now modeled on RunState (run.project, bare name) and persisted as a
column on the runs table. This route aggregates the run list per project so the
cockpit can present a project switcher instead of a flat run list:

  GET /projects →
    [{ project, run_count, active_run_id, last_created_at, runs: [...] }]

sorted by most recent activity desc (projects with no runs yet last). The status
of each run is the same live-truth merge as GET /runs: in-memory beats the
persisted column, and a persisted 'running' with no active loop means the engine
restarted → 'paused'. Project directories under <harness_root>/projects/ that
have zero runs still appear (runs: [], run_count: 0) so a freshly-scaffolded
project is visible before its first run.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from ..orchestrator import get_run
from ..persistence import list_runs
# Harness-root / project-dir validation is content_progress' — reuse it (module
# reference, not a from-import, so tests can monkeypatch _harness_root exactly
# like test_content_progress does).
from . import content_progress

log = logging.getLogger(__name__)

router = APIRouter()


def effective_status(row: dict) -> str:
    """Live-truth status for a persisted run row — the exact GET /runs
    normalization: in-memory beats the column; a persisted 'running' with no
    active loop means the engine restarted → 'paused'."""
    mem = get_run(row["run_id"])
    if mem:
        return mem.status.value
    if row["status"] == "running":
        return "paused"
    return row["status"]


@router.get("/projects")
async def get_projects():
    """All projects with their runs grouped, plus zero-run project directories.
    active_run_id = a run of the project whose EFFECTIVE (live-merged) status is
    running — the guard POST /runs uses to warn about concurrent runs."""
    groups: dict[str | None, list[dict]] = {}
    for r in await list_runs():
        r = dict(r)
        r["status"] = effective_status(r)
        groups.setdefault(r.get("project"), []).append(r)

    out: list[dict] = []
    for project, runs in groups.items():
        runs.sort(key=lambda r: r["created_at"] or 0, reverse=True)
        out.append({
            "project": project,
            "run_count": len(runs),
            "active_run_id": next((r["run_id"] for r in runs if r["status"] == "running"), None),
            "last_created_at": max((r["created_at"] for r in runs if r["created_at"] is not None),
                                   default=None),
            "runs": runs,
        })

    # Zero-run project directories (scaffolded but never run) — traversal-safe by
    # construction: only bare directory names that _valid_project accepts, joined
    # under the harness root's projects/ dir.
    projects_dir = content_progress._harness_root() / "projects"
    if projects_dir.is_dir():
        known = {g["project"] for g in out}
        for entry in sorted(projects_dir.iterdir()):
            name = entry.name
            if not entry.is_dir() or name.startswith(".") or not content_progress._valid_project(name):
                continue
            if name in known:
                continue
            out.append({"project": name, "run_count": 0, "active_run_id": None,
                        "last_created_at": None, "runs": []})

    out.sort(key=lambda g: g["last_created_at"] or 0, reverse=True)
    return out
