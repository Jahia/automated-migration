from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats")
async def get_stats() -> dict:
    """Global token/cost counter (P5.5): aggregated from the per-step counters of
    every in-memory run — the direct-API usage accumulated in _execute_single_step
    / run_repair_agent. Same response shape the UI's TokenCounter expects. There
    are no agent "sessions" anymore; `sessions` reports the run count instead."""
    from ..orchestrator import _runs

    total = {
        "input": 0,
        "output": 0,
        "reasoning": 0,
        "cache_read": 0,
        "cache_write": 0,
        "cost": 0.0,
        "sessions": 0,
    }
    try:
        total["sessions"] = len(_runs)
        for run in _runs.values():
            for epic in run.epics:
                for story in epic.stories:
                    for step in story.steps:
                        total["input"] += step.tokens_in
                        total["output"] += step.tokens_out
                        total["cache_read"] += step.tokens_cache
                        total["cost"] += step.cost
    except Exception as e:  # noqa: BLE001
        log.warning(f"Failed to aggregate stats: {e}")
    return total


@router.get("/runs/{run_id}/stats")
async def get_run_stats(run_id: str) -> dict:
    """Per-run aggregated stats from the audit log."""
    from ..orchestrator import get_run
    from ..models import StepStatus

    run = get_run(run_id)
    if not run:
        return {"error": "run not found"}

    total_tokens_in = 0
    total_tokens_out = 0
    total_tokens_cache = 0
    total_cost = 0.0
    total_steps = 0
    done_steps = 0
    failed_steps = 0
    total_duration_ms = 0
    step_details = []

    for epic in run.epics:
        for story in epic.stories:
            for step in story.steps:
                total_steps += 1
                total_tokens_in += step.tokens_in
                total_tokens_out += step.tokens_out
                total_tokens_cache += step.tokens_cache
                total_cost += step.cost
                if step.duration_ms:
                    total_duration_ms += step.duration_ms
                if step.status == StepStatus.done:
                    done_steps += 1
                elif step.status == StepStatus.failed:
                    failed_steps += 1
                step_details.append({
                    "step_id": step.id,
                    "epic_id": epic.id,
                    "story_id": story.id,
                    "status": step.status.value,
                    "attempt": step.attempt,
                    "tokens_in": step.tokens_in,
                    "tokens_out": step.tokens_out,
                    "cost": step.cost,
                    "duration_ms": step.duration_ms,
                    "task_type": step.task_type,
                })

    # Read audit log if available
    audit_entries = []
    audit_file = Path(f"/tmp/orch-audit/{run_id}.jsonl")
    if audit_file.exists():
        try:
            with open(audit_file) as f:
                for line in f:
                    if line.strip():
                        audit_entries.append(json.loads(line))
        except Exception as e:
            log.warning(f"Failed to read audit log: {e}")

    return {
        "run_id": run_id,
        "status": run.status.value,
        "total_steps": total_steps,
        "done_steps": done_steps,
        "failed_steps": failed_steps,
        "success_rate": done_steps / total_steps if total_steps else 0,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_tokens_cache": total_tokens_cache,
        "total_cost": total_cost,
        "total_duration_ms": total_duration_ms,
        "steps": step_details,
        "audit_events_count": len(audit_entries),
    }


@router.get("/runs/{run_id}/audit")
async def get_run_audit(run_id: str, event_type: str | None = None, limit: int = 100) -> list[dict]:
    """Read the structured audit log for a run.

    Optional filters:
    - event_type: filter by event type (e.g. step_failed, probe_executed)
    - limit: max entries to return (default 100)
    """
    audit_file = Path(f"/tmp/orch-audit/{run_id}.jsonl")
    if not audit_file.exists():
        return []

    entries = []
    try:
        with open(audit_file) as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if event_type and entry.get("event") != event_type:
                    continue
                entries.append(entry)
    except Exception as e:
        log.warning(f"Failed to read audit log: {e}")
        return []

    return entries[-limit:]
