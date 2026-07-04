"""content_progress.py — read-only observability for step_content_load (Julian, 2026-07-04).

The content-load step creates hundreds of page/instance/media nodes over many
minutes. `orchestration/assist/content_watch.sh` runs the integrity belt on a
fixed cadence and appends one JSONL tick per pass to
    projects/<project>/workflow-output/content-progress.jsonl
each of shape {"ts","expected","created","pct","pagesStarted","pagesTotal","media"}.

This endpoint is a PURE FILE READER over that ticker (plus a light summary of the
belt's integrity-report.json). It makes NO network call to Jahia — no credentials
live in the web tier, no latency, safe to poll mid-step. The cockpit consumes it
observability-only (commit 3388ee4): it never pilots the run.

  GET /projects/{project}/content-progress?limit=50
    → {"ticks": [<last N ticks>], "latest": <last tick|null>, "report": <summary|null>}

Validation: `project` must be a bare segment (no '/', no '..', no absolute path) —
it is joined under the repo-root projects/ dir and MUST NOT escape it. 404 when the
project dir does not exist; empty-but-valid payload when the ticker has not written yet.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

log = logging.getLogger(__name__)

router = APIRouter()


def _harness_root() -> Path:
    """The jahiaMigration repo root (src/routes/ → src/ → migration-orchestrator/ → root)."""
    return Path(__file__).resolve().parents[3]


def _valid_project(project: str) -> bool:
    """A safe project segment: non-empty, no separators, no traversal, no absolute path.
    The ONLY accepted shape is a single path component (e.g. 'discoverasr')."""
    if not project or project in (".", ".."):
        return False
    if "/" in project or "\\" in project or "\x00" in project:
        return False
    # a single, normalized path component only (defence in depth vs. the checks above)
    return Path(project).name == project


def _project_dir(project: str) -> Path:
    return _harness_root() / "projects" / project


def _read_ticks(jsonl: Path, limit: int) -> list[dict]:
    """Last `limit` valid ticks from the JSONL ticker (skip blank/corrupt lines)."""
    if not jsonl.is_file():
        return []
    ticks: list[dict] = []
    try:
        with open(jsonl) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ticks.append(json.loads(line))
                except (ValueError, TypeError):
                    continue  # a half-written line while the ticker appends
    except OSError as e:
        log.warning(f"content-progress: could not read {jsonl}: {e}")
        return []
    return ticks[-limit:] if limit and limit > 0 else ticks


def _report_summary(report_json: Path) -> dict | None:
    """Light summary of the integrity belt's report (never the full blob):
    ranAt, phase, mismatchCount, and the page-tree section if present."""
    if not report_json.is_file():
        return None
    try:
        with open(report_json) as f:
            r = json.load(f)
    except (OSError, ValueError) as e:
        log.warning(f"content-progress: could not read {report_json}: {e}")
        return None
    return {
        "ranAt": r.get("ranAt"),
        "phase": r.get("phase"),
        "mismatchCount": len(r.get("mismatches") or []),
        "pages": (r.get("sections") or {}).get("pages"),
    }


def read_content_progress(project: str, limit: int = 50) -> dict:
    """Pure reader: ticker + report summary for a project's workflow-output.
    Raises HTTPException(404) when the project directory does not exist."""
    wo = _project_dir(project) / "workflow-output"
    if not _project_dir(project).is_dir():
        raise HTTPException(status_code=404, detail=f"project not found: {project}")
    ticks = _read_ticks(wo / "content-progress.jsonl", limit)
    return {
        "project": project,
        "ticks": ticks,
        "latest": ticks[-1] if ticks else None,
        "report": _report_summary(wo / "integrity-report.json"),
    }


@router.get("/projects/{project}/content-progress")
async def get_content_progress(project: str, limit: int = 50) -> dict:
    """Read-only content-load progress: the last `limit` ticker samples, the latest
    one, and a light integrity-report summary. No Jahia call — pure file read."""
    if not _valid_project(project):
        raise HTTPException(status_code=400, detail="invalid project name")
    return read_content_progress(project, limit)
