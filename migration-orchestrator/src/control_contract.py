"""control_contract — make the orchestrator SELF-DESCRIBING so ANY LLM can drive it.

Two layers:
  * CONTROL_CONTRACT (served at GET /control): the static "how" — the control loop,
    the endpoint catalog with WHEN to call each, the decision protocol, the hard
    boundaries. An agent reads this ONCE to learn to pilot.
  * gate_review() + rich_actions() (injected into every run status by compact_status):
    the per-state "what now" — the exact calls available at THIS gate, the artifacts
    to review, so each poll is self-sufficient.

Design goal (Julian, 2026-07-05): an LLM drives with zero out-of-band knowledge —
GET /control once, then loop on GET /runs/{id} doing what its `control` block says.
"""

CONTROL_CONTRACT = {
    "purpose": (
        "Drive a Jahia website-migration run to completion. The ENGINE executes each "
        "step deterministically and PAUSES at gates for a decision. You (any LLM) make "
        "that decision through this audited API. You NEVER run the pipeline by hand."
    ),
    "loop": [
        "1. GET /runs/{id} → read `status`, `control.gate`, `control.quality`, `control.review`, `control.actions`.",
        "2. status=running → poll again (optionally GET /runs/{id}/logs).",
        "3. A gate/decision is active → OPEN every URL in `control.review`, read `quality.verdict`+`reasons`, then take EXACTLY ONE action from `control.actions` (the only way past a gate).",
        "4. status=failed → read `last_error`, then rerun the failing step or rollback.",
        "5. Repeat until status=done.",
    ],
    "endpoints": [
        {"call": "GET /runs/{id}", "when": "always — the current state and what to do next (has the `control` block)"},
        {"call": "GET /runs/{id}/quality", "when": "detail on the current gate verdict (green/amber/red + metrics + reasons)"},
        {"call": "GET /runs/{id}/logs", "when": "a step is running or failed and you need its output"},
        {"call": "GET /runs/{id}/artifacts/{path}", "when": "open an observability artifact listed in `control.review`"},
        {"call": "POST /runs/{id}/steps/{step}/decide {action, reason}", "when": "a decision/gate is pending; action ∈ [proceed, retry, apply_and_rerun, repatch]"},
        {"call": "POST /runs/{id}/steps/{step}/rerun {reason}", "when": "you fixed that STEP'S CODE and want it re-executed with the fix (resets dependents; upstream steps like the mirror are NOT re-run)"},
        {"call": "POST /runs/{id}/gate {decision, reason}", "when": "legacy gate decision (approve|reject|rerun) — prefer /decide"},
        {"call": "POST /runs/{id}/rollback {to_step, reason}", "when": "go back to an earlier step and redo from there"},
        {"call": "POST /runs/{id}/pause | /resume | /abort", "when": "control the loop lifecycle"},
    ],
    "decide_actions": {
        "proceed": "accept the gate as-is and continue — the mirror/model/fidelity is good enough",
        "retry": "re-run the step unchanged (a transient failure)",
        "apply_and_rerun": "you changed the step's inputs/rules; re-run with them applied",
        "repatch": "supply corrected step inputs (audited; smuggling acceptance_criteria/PROBE lines is a tripwire)",
    },
    "boundaries": [
        "EDIT-only: never publish per-node during the process. Publication is a SINGLE FINAL human act (unpublish-first).",
        "Drive ONLY via this API. Never hand-run load/deploy/site-create/docker-restart. A harness CODE fix is committed, then the step is re-executed via POST .../rerun.",
        "All verification runs against the EDIT workspace (authenticated preview). No test ever touches LIVE.",
        "Never generate site content (nor LLM translations). Only editor-UI labels/tooltips may be generated.",
        "A gate is the only halt→proceed path; every decision is audited (gate_decision / rerun_step / rollback events).",
        "Fidelity target: 0-DOM-change (visible DOM structurally identical to the source mirror) — stronger than pixels.",
    ],
    "gates": {
        "mirror": "the page renders fully offline from the local mirror (client-rendered SPAs correctly refused).",
        "model": "the component model: meaningful content types, clean zones (content-free containers), low genericShare, no <main>/wrapper double.",
        "fidelity": "deployed EDIT render ≥ threshold pixel-identical to the frozen mirror, per page.",
        "groundtruth": "same as fidelity — deployed vs mirror.",
        "contribution": "G1/G5: editable coverage, media→DAM, links→j:linkType, 0 dead/empty/phantom.",
        "deploy": "the module bundle is ACTIVE and the nodetypes actually resolved.",
        "content": "content created; publication is the final human act.",
    },
}

# gate_type → observability artifacts to review (relative to /runs/{id}/artifacts/)
_GATE_REVIEW = {
    "mirror": ["mirror/mirror-check.json", "local-mirror/mirror.json"],
    "model": ["zone-review.html", "zone-overlay/index.html", "component-manifest.json"],
    "fidelity": ["visual-diff/SUMMARY.md"],
    "groundtruth": ["visual-diff/SUMMARY.md"],
    "contribution": ["review/REVIEW.md"],
    "segmentation": ["zone-overlay/index.html", "component-manifest.json"],
}


def gate_review(run_id: str, gate_type: str | None) -> list[str]:
    """Artifact URLs an LLM should open before deciding this gate."""
    paths = _GATE_REVIEW.get(gate_type or "", [])
    return [f"/runs/{run_id}/artifacts/{p}" for p in paths]


def rich_actions(run_id: str, actions: list[str], gate) -> list[dict]:
    """Turn bare action names into self-describing calls (verb+path+when)."""
    sid = gate.id if gate is not None else "{step}"
    catalog = {
        "decide": {"call": f"POST /runs/{run_id}/steps/{sid}/decide {{action, reason}}",
                   "when": "make the gate decision; action ∈ [proceed, retry, apply_and_rerun, repatch]"},
        "approve": {"call": f"POST /runs/{run_id}/gate {{decision:'approve', reason}}",
                    "when": "the gate is good — proceed"},
        "reject": {"call": f"POST /runs/{run_id}/gate {{decision:'reject', reason}}",
                   "when": "the gate is not acceptable — send it back"},
        "rerun": {"call": f"POST /runs/{run_id}/steps/{sid}/rerun {{reason}}",
                  "when": "you fixed this step's CODE — re-execute it (resets dependents; upstream not re-run)"},
        "rollback": {"call": f"POST /runs/{run_id}/rollback {{to_step, reason}}",
                     "when": "go back to an earlier step and redo from there"},
        "jump": {"call": f"POST /runs/{run_id}/jump {{step_id, reset_dependents}}",
                 "when": "force the run to a specific step"},
        "restart": {"call": f"POST /runs/{run_id}/restart",
                    "when": "restart the whole run from scratch"},
        "start": {"call": f"POST /runs/{run_id}/start", "when": "begin the run"},
        "pause": {"call": f"POST /runs/{run_id}/pause", "when": "pause the loop"},
        "wait": {"call": f"GET /runs/{run_id}", "when": "a step is running — poll again"},
    }
    out = [dict(action=a, **catalog[a]) for a in actions if a in catalog]
    # the rerun verb is ALWAYS available at a gate/decision (fix code → re-execute),
    # not just for the fidelity gate — surface it explicitly.
    if gate is not None and not any(o["action"] == "rerun" for o in out):
        out.append(dict(action="rerun", **catalog["rerun"]))
    return out
