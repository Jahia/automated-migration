"""migration_control.py — the LLM/agent control surface for migration runs.

The generic engine already exposes create/start/pause/resume/jump/abort + full
state + SSE. This module adds the *decision-relevant* projection an autonomous
agent needs to drive a migration without parsing the whole run tree:

  - compact_status(run): phase, current step, active gate, quality verdict, cost,
    progress, and the set of next actions available.
  - quality_verdict(run, gate_type): a green/amber/red verdict computed from the
    run's artifacts (reconstruct.json coverage, component-manifest, candidates) —
    the signal an 'assisted' agent uses to auto-approve or escalate.
  - log_tail(run, since): a poll-friendly log (recent events + active streaming +
    errors) as an alternative to the SSE stream.

Pure/read-only: side effects (resume/pause/jump/rerun, decision audit) stay in the
route handlers. See CONTROL-LOOP.md for the poll→decide→act contract.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from .models import RunState, StepState

# Mirrors the frontend MIGRATION_PHASES (migration/types.ts) — keep in sync.
PHASES: list[tuple[str, str, list[str]]] = [
    ("capture", "Capture", ["crawl", "capture"]),
    ("mirror", "Local mirror", ["localize", "mirror"]),
    ("analyze", "Analyze", ["extract", "semantic", "analyze", "block"]),
    ("model", "Model components", ["group", "component_model", "assemble", "discover", "cluster", "cnd", "content_type"]),
    ("fidelity", "Fidelity gate", ["reconstruct", "fidelity"]),
    ("scaffold", "Scaffold module", ["scaffold"]),
    ("implement", "Implement + templates", ["implement", "navigation", "jcr", "grid", "component", "template"]),
    ("content", "Content + publish", ["content", "create", "publish"]),
    ("golive", "Go-live · visual diff", ["visual", "vanity", "golive", "review", "accessibility"]),
]

# 'rejected' is a blocking gate too: the run stays paused until the operator
# redoes the step (jump/rollback) — hiding it gives the LLM pilot a dead end.
_GATE_STATUSES = {"halted", "waiting_human", "rejected"}


def all_steps(run: RunState) -> list[StepState]:
    return [st for e in run.epics for s in e.stories for st in s.steps]


def phase_of(step_id: str) -> dict:
    sid = (step_id or "").lower()
    for key, title, needles in PHASES:
        if any(n in sid for n in needles):
            return {"key": key, "title": title}
    return {"key": "?", "title": "?"}


def active_gate(steps: list[StepState]) -> StepState | None:
    return next((s for s in steps if s.status.value in _GATE_STATUSES and s.gate_type), None)


def pending_decision(steps: list[StepState]) -> StepState | None:
    """A decision_pending step (ASSIST-PLAN §3): retries exhausted with
    strategies left, or a scheduled review checkpoint. Decided via /decide."""
    return next((s for s in steps if s.status.value == "decision_pending"), None)


def project_path(run: RunState) -> str | None:
    """The project dir this run migrates (from any step's inputs)."""
    for s in all_steps(run):
        pp = s.inputs.get("project_path") or s.inputs.get("project")
        if pp:
            return str(pp)
    return None


def workflow_output_dir(run: RunState) -> Path | None:
    pp = project_path(run)
    return (Path(run.repo_dir) / pp / "workflow-output") if pp else None


# ── quality verdict — green/amber/red from artifacts ──────────────

def _verdict_fidelity(wo: Path) -> dict | None:
    f = wo / "reconstruct" / "reconstruct.json"
    if not f.is_file():
        return None
    d = json.loads(f.read_text())
    pages = d.get("pages", [])
    covs = [p["contentCoverage"] for p in pages if p.get("contentCoverage") is not None]
    thr = d.get("threshold", 95)
    if not covs:
        return {"verdict": "unknown", "gate": "fidelity", "metrics": {}, "reasons": ["no page coverage yet"]}
    worst = min(covs)
    pix = [p.get("pixelSimilarity") for p in pages if p.get("ok") and p.get("pixelSimilarity") is not None]
    real_orphans = sum(1 for p in pages for o in (p.get("orphanSamples") or []) if not o.get("ignorable"))
    verdict = "green" if worst >= thr else ("amber" if worst >= thr - 5 else "red")
    reasons = [f"worst content coverage {worst}% vs threshold {thr}%"]
    if real_orphans:
        reasons.append(f"{real_orphans} real uncaptured text fragment(s)")
    return {"verdict": verdict, "gate": "fidelity", "metrics": {
        "worstContentCoverage": worst, "threshold": thr, "pages": len(covs),
        "avgPixelSim": round(mean(pix), 1) if pix else None, "realOrphans": real_orphans,
    }, "reasons": reasons}


def _verdict_mirror(wo: Path) -> dict | None:
    f = wo / "mirror" / "mirror-check.json"
    if not f.is_file():
        return None
    d = json.loads(f.read_text())
    pages = d.get("pages", [])
    misses = sum((p.get("realMissCount") or 0) + (p.get("localMissCount") or 0) for p in pages)
    repaired = sum(p.get("runtimeRepaired") or 0 for p in pages)
    fid = [p.get("mirrorFidelity") for p in pages if p.get("mirrorFidelity") is not None]
    gate = bool(d.get("gatePass"))
    verdict = "green" if gate else ("amber" if misses <= 3 else "red")
    reasons = ["mirror renders fully offline" if gate else f"{misses} asset(s) still missing offline"]
    if repaired:
        reasons.append(f"{repaired} runtime asset(s) captured by repair")
    return {"verdict": verdict, "gate": "mirror", "metrics": {
        "gatePass": gate, "pages": len(pages), "misses": misses, "runtimeRepaired": repaired,
        "worstMirrorFidelity": min(fid) if fid else None,
    }, "reasons": reasons}


def _verdict_model(wo: Path) -> dict | None:
    f = wo / "component-manifest.json"
    if not f.is_file():
        return None
    m = json.loads(f.read_text())
    comps = m.get("components", [])
    mr = sum(1 for c in comps if c.get("needsMainResource"))
    violations = m.get("namingViolations", [])
    quality = m.get("namingQuality", "good" if not violations else "mixed")
    # editorial naming quality gates the verdict: a structurally-fine model whose
    # type names leak CSS hashes / bare tags is not shippable to an editor.
    if not comps:
        verdict = "amber"
    elif quality == "poor":
        verdict = "red"
    elif quality == "mixed":
        verdict = "amber"
    else:
        verdict = "green"
    reasons = [f"{len(comps)} content types, {mr} mainResource, {len(m.get('crossCutting', []))} cross-cutting"]
    if violations:
        reasons.append(f"naming: {quality} — {len(violations)} editor-hostile type name(s) "
                       f"(e.g. {', '.join(v['nodeType'] for v in violations[:3])})")
    return {"verdict": verdict, "gate": "model", "metrics": {
        "types": len(comps), "templates": len(m.get("templates", [])),
        "crossCutting": len(m.get("crossCutting", [])), "mainResource": mr,
        "namingQuality": quality, "namingViolations": len(violations),
    }, "reasons": reasons}


def _verdict_scope(wo: Path) -> dict | None:
    f = wo / "semantic-candidates.json"
    if not f.is_file():
        return None
    d = json.loads(f.read_text())
    n = len(d.get("components", [])) + len(d.get("crossCutting", []))
    return {"verdict": "green" if d.get("components") else "amber", "gate": "scope", "metrics": {
        "candidates": n, "crossCutting": len(d.get("crossCutting", [])),
        "detailTemplates": len(d.get("detailTemplates", [])),
    }, "reasons": [f"{n} candidates extracted"]}


def quality_verdict(run: RunState, gate_type: str | None, wo: Path | None) -> dict:
    """Verdict for the active gate (or the furthest-available artifact)."""
    if not wo or not wo.exists():
        return {"verdict": "unknown", "metrics": {}, "reasons": ["no workflow-output yet"]}
    by_gate = {
        "fidelity": [_verdict_fidelity],
        "mirror": [_verdict_mirror],
        "model": [_verdict_model],
        "scope": [_verdict_scope],
        "content": [_verdict_model],
        "golive": [_verdict_fidelity, _verdict_model],
    }
    if gate_type and gate_type in by_gate:
        for fn in by_gate[gate_type]:
            r = fn(wo)
            if r:
                return r
    for fn in (_verdict_fidelity, _verdict_model, _verdict_scope):  # furthest available
        r = fn(wo)
        if r:
            return r
    return {"verdict": "unknown", "metrics": {}, "reasons": ["no artifacts yet"]}


# ── compact status ────────────────────────────────────────────────

def _decision_summary(step: StepState) -> str:
    if step.review:
        return f"review checkpoint: {step.title}"
    remaining = [s.id for s in step.strategies if s.id not in step.strategies_applied]
    err = ""
    if step.verification and step.verification.errors:
        err = "; ".join(step.verification.errors)[:200]
    elif step.agent_result and step.agent_result.summary:
        err = step.agent_result.summary[:200]
    return (f"retries exhausted ({step.attempt}/{step.max_attempts}); "
            f"strategies remaining: {', '.join(remaining) or 'none'}"
            + (f" — {err}" if err else ""))


def _last_error(steps: list[StepState]) -> str | None:
    for s in reversed(steps):
        if s.status.value == "failed":
            if s.verification and s.verification.errors:
                return "; ".join(s.verification.errors)[:500]
            if s.agent_result and s.agent_result.summary:
                return s.agent_result.summary[:500]
            return f"step {s.id} failed"
    return None


def compact_status(run: RunState, wo: Path | None) -> dict:
    steps = all_steps(run)
    running = next((s for s in steps if s.status.value == "running"), None)
    gate = active_gate(steps)
    decision = pending_decision(steps)
    cur = running or gate or decision or next((s for s in reversed(steps) if s.agent_result or s.streaming_text), None)
    done = [s for s in steps if s.status.value == "done"]
    q = quality_verdict(run, gate.gate_type if gate else None, wo)

    if decision and not gate:
        # a pending decision point: decided ONLY via POST /steps/{id}/decide
        actions = ["decide", "rollback", "restart"]
    elif gate and gate.status.value == "rejected":
        # a rejected gate cannot be approved anymore — only redone or restarted
        actions = ["rollback", "jump", "restart"]
    elif gate:
        actions = ["approve", "reject", "rollback"] + (["rerun"] if gate.gate_type == "fidelity" else [])
    elif run.status.value == "failed":
        actions = ["rollback", "restart"]
    elif run.status.value == "running":
        actions = ["wait", "pause"]
    elif run.status.value == "created":
        actions = ["start"]
    else:
        actions = []

    return {
        "run_id": run.run_id,
        "goal": run.goal,
        "status": run.status.value,
        "autonomy": getattr(run, "autonomy", "assisted"),
        "phase": phase_of(cur.id) if cur else {"key": "?", "title": "?"},
        "current_step": ({"id": cur.id, "title": cur.title, "status": cur.status.value,
                          "attempt": cur.attempt} if cur else None),
        "gate": ({"active": True, "type": gate.gate_type, "step_id": gate.id,
                  "status": gate.status.value,
                  "summary": (gate.agent_result.summary if gate.agent_result else "")} if gate
                 else ({"active": True, "type": "decision", "step_id": decision.id,
                        "status": "decision_pending",
                        "summary": _decision_summary(decision)} if decision else None)),
        "quality": q,
        "progress": {"steps_done": len(done), "steps_total": len(steps),
                     "pct": round(100 * len(done) / len(steps)) if steps else 0},
        "cost": round(sum(s.cost for s in steps), 4),
        "tokens_out": sum(s.tokens_out for s in steps),
        "last_error": _last_error(steps),
        "updated_at": run.updated_at,
        "next_actions": actions,
    }


# ── log tail (poll-friendly alternative to SSE) ───────────────────

def _short(payload: dict) -> str:
    for k in ("summary", "message", "status", "reason", "command", "detail"):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v[:200]
    return json.dumps(payload)[:200] if payload else ""


def log_tail(run: RunState, since: float = 0.0, limit: int = 50) -> dict:
    steps = all_steps(run)
    events = []
    for s in steps:
        for ev in (s.trace or []):
            events.append({"ts": ev.timestamp, "seq": ev.seq, "step_id": s.id,
                           "type": ev.type, "summary": _short(ev.payload)})
    events.sort(key=lambda e: (e["ts"], e["seq"]))
    fresh = [e for e in events if e["ts"] > since] if since else events[-limit:]
    fresh = fresh[:limit]
    cursor = max((e["ts"] for e in events), default=since)

    active = next((s for s in steps if s.status.value in ("running", "verifying")), None) \
        or next((s for s in reversed(steps) if s.streaming_text), None)
    active_out = None
    if active:
        txt = active.streaming_text or (active.agent_result.summary if active.agent_result else "")
        active_out = {"step_id": active.id, "status": active.status.value, "tail": txt[-2000:]}

    errors = [{"step_id": s.id, "detail": (
        "; ".join(s.verification.errors) if (s.verification and s.verification.errors)
        else (s.agent_result.summary if s.agent_result else "failed"))[:300]}
        for s in steps if s.status.value == "failed"]

    return {"cursor": cursor, "count": len(fresh), "events": fresh,
            "active_step": active_out, "errors": errors}
