# Driving a migration from an LLM — the control-loop contract

The migration cockpit is drivable by a human (the web UI) **and** by an LLM/agent
over the same REST API. This is the poll→decide→act contract an agent follows. The
engine stays the dumb executor; the agent is the brain that reads quality signals
and decides whether to advance, escalate to a human, or roll back.

Same-origin base = the engine (default `http://localhost:8001`).

---

## The surface

| Verb | Path | Purpose |
|---|---|---|
| `POST` | `/migrations` | create a run from the fixed analyze plan (site facts + `autonomy`) → `{run_id}` |
| `POST` | `/runs/{id}/start` | launch it |
| `GET` | `/runs/{id}/status` | **compact** status — the poll target (below) |
| `GET` | `/runs/{id}/quality` | the green/amber/red verdict alone (active gate) |
| `GET` | `/runs/{id}/log?since=<ts>&limit=N` | poll-friendly log tail (events + streaming + errors) |
| `POST` | `/runs/{id}/gate` | `{decision: approve\|reject\|rerun, reason, pages?}` — typed, **audited** gate decision |
| `POST` | `/runs/{id}/rollback` | `{to_step, reason}` — re-run from an earlier step, reset dependents (audited) |
| `GET` | `/runs/{id}/artifacts/{path}` | raw artifact (e.g. `reconstruct/reconstruct.json`, `component-manifest.json`) |
| `POST` | `/runs/{id}/pause` · `/resume` · `/abort` | lifecycle |

`gate approve` = `resume` (the engine forces the halted step to done); the typed
endpoint additionally records the decision + reason to the event log for audit.

### `GET /runs/{id}/status` (the poll target)

```jsonc
{
  "status": "running|paused|completed|failed|created|aborted",
  "autonomy": "assisted",
  "phase": {"key": "fidelity", "title": "Fidelity gate"},
  "current_step": {"id": "step_reconstruct_gate", "status": "halted", "attempt": 0},
  "gate": {"active": true, "type": "fidelity", "step_id": "…", "summary": "…"} | null,
  "quality": {
    "verdict": "green|amber|red|unknown",
    "gate": "fidelity",
    "metrics": {"worstContentCoverage": 100, "threshold": 95, "avgPixelSim": 98.7, "realOrphans": 1},
    "reasons": ["worst content coverage 100% vs threshold 95%"]
  },
  "progress": {"steps_done": 4, "steps_total": 5, "pct": 80},
  "cost": 0.08, "tokens_out": 20000,
  "last_error": null,
  "next_actions": ["approve", "reject", "rollback", "rerun"]
}
```

`next_actions` is the engine's hint for what is currently legal — always prefer it
over guessing from `status`.

---

## Quality verdict

Computed deterministically from the run's artifacts (never from an LLM):

| Gate | Source | green | amber | red |
|---|---|---|---|---|
| `scope` | `semantic-candidates.json` | candidates present | — | none |
| `model` | `component-manifest.json` | ≥1 content type | 0 types | — |
| `fidelity` | `reconstruct/reconstruct.json` | worst coverage ≥ threshold | ≥ threshold−5 | below |

`fidelity` is the decisive gate: `verdict` is green only when **every** sampled page
captured all its content. `realOrphans > 0` means real (non-chrome) text went
uncaptured — treat as a reason to inspect even if coverage rounds to green.

---

## Autonomy levels

Set per migration at `POST /migrations` (`autonomy`), surfaced in `status.autonomy`.
It governs the **agent's** behaviour at a gate — the engine does not auto-advance.

- **manual** — the agent observes and reports. Every gate decision is a human's.
- **assisted** *(default)* — the agent **auto-approves a green gate** and **escalates
  amber/red to a human** (pause + a clear summary of the failing metric). This is the
  balance of speed and control.
- **autonomous** — the agent decides all gates. It still escalates on `red`, on a
  step `failed` it can't resolve by one rollback, or on repeated non-progress.

---

## The loop

```
run_id = POST /migrations {site_url, project, ns, autonomy}
POST /runs/{run_id}/start
loop:
  s = GET /runs/{run_id}/status
  if s.status in {completed, aborted}: done
  if s.status == failed:
      diagnose via GET /log; POST /rollback {to_step: <earlier good step>} once;
      if still failed → escalate to human
  if s.gate.active:
      v = s.quality.verdict
      if   v == green  and autonomy != manual:  POST /gate {approve}
      elif v in {amber, red} or autonomy == manual:
           escalate to human with s.quality.reasons  (or POST /gate {rerun,pages}
           after fixing an extraction gap; then re-poll)
      else: POST /gate {approve}          # unknown + autonomous: proceed cautiously
  else:
      wait (poll interval ~2–5s); tail GET /log?since=<cursor> for narration
```

Rules of thumb for an assisted agent:
- **Never approve a red gate.** Escalate with the metric that failed.
- **Amber is a human call** — surface `quality.reasons`, don't auto-approve.
- **One rollback, then escalate.** Don't loop rollbacks; a second failure is a human's.
- **Record why.** Every `gate`/`rollback` carries a `reason`; it lands in the event log.
- **Fidelity rerun** (`gate {rerun, pages}`) is for after you've fixed an extraction
  gap and want to re-verify a page sample — not a retry of the same inputs.

See the fixed pipeline + gates in [`../orchestration/ANALYZE-PIPELINE.md`](../orchestration/ANALYZE-PIPELINE.md)
and the cockpit UI in [`frontend/MIGRATION_PROFILE.md`](frontend/MIGRATION_PROFILE.md).
