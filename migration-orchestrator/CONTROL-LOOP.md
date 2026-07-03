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

**Gate decisions are explicit and typed — a plain `resume` never decides a gate.**

- `gate {approve}` — the ONLY path that turns a halted step into `done` (then the
  run resumes). Recorded with its reason in the event log for audit.
- `gate {reject}` — the halted step becomes **`rejected`**, a persistent step state
  (survives engine restarts). The run stays paused: a rejected step behaves like a
  failed step with no retries left, until the operator uses `jump`/`rollback` to
  redo it (jump to the rejected step resets it to re-run).
- `POST /runs/{id}/resume` with a `halted` or `rejected` step present is refused:
  the run stays paused and the engine logs which step blocks it and what to do
  (approve/reject via the gate endpoint, or jump/rollback). Resuming is never a
  silent approval.

### `GET /runs/{id}/status` (the poll target)

```jsonc
{
  "status": "running|paused|completed|failed|created|aborted",
  "autonomy": "assisted",
  "phase": {"key": "fidelity", "title": "Fidelity gate"},
  "current_step": {"id": "step_reconstruct_gate", "status": "halted", "attempt": 0},
  "gate": {"active": true, "type": "fidelity", "step_id": "…", "status": "halted|waiting_human|rejected", "summary": "…"} | null,
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
over guessing from `status`. A **rejected** gate is still surfaced as the blocking
gate (`gate.status: "rejected"`) with `next_actions: ["rollback", "jump", "restart"]` —
it cannot be approved anymore; jump/rollback to the step redoes it.

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

## Engine integrity + recovery semantics (learned 2026-07-02, 3-site batch)

- **PROBEs are engine-enforced.** `verifier.py` extracts every `PROBE:` line from the
  step's acceptance criteria and executes them itself — the agent's self-report can
  neither skip nor excuse a failing probe. Before this, enforcement depended on the
  agent *choosing* to declare the probe in `commands_requested` (observed: one
  DeepSeek agent halted honestly on a red gate, another sailed past it).
- **Probe timeouts.** Default per-probe timeout comes from `ORCHESTRATOR_PROBE_TIMEOUT`
  (seconds, fallback 600). `PROBE[NNN]: <cmd>` overrides it per probe — use it for
  probes that legitimately outlast the default (a cold `yarn install && yarn build`).
  Agent-declared `commands_requested` always get the default.
- **Plan lint at creation.** `POST /runs` and `POST /migrations` reject (HTTP 400) any
  plan whose steps match `/(deploy|content|publish|scaffold)/i` on id or title without
  at least one `PROBE:` line in `acceptance_criteria` — the error lists the offending
  steps. Any other step with zero PROBEs is only logged as a warning (it auto-passes
  on the agent's self-report).
- **`gate` vs `resume` vs `jump` vs `restart`** — four different tools:
  - `POST /runs/{id}/gate {approve|reject}` — decides a halted gate (see above).
    Approve is the only halted→done path; reject persists a `rejected` step state.
  - `POST /runs/{id}/resume` — resumes paused AND recovers failed runs, but is
    REFUSED while a step is halted or rejected (clear log line; run stays paused).
    On a fresh loop (engine restarted since), it normalizes state first: orphaned
    running/verifying/failed steps → **pending** (not `ready`: despite its name,
    `select_next_ready_step` only picks *pending* steps — `ready` is jump's forced
    state), failed story/epic with runnable steps → pending. Halted/rejected steps
    are never normalized. Without this, resuming a failed run re-fails in ~20 ms.
  - `POST /runs/{id}/jump {step_id}` — reset a specific step + dependents and force it
    next. Use to REDO a halted gate instead of approving it, and to redo a rejected one.
  - `POST /runs/{id}/restart` — full reset (all steps pending), full re-run. Cheap when
    the crawl cache + mirror already exist (cache-first).
- **A run-level `failed` with parallel branches is not what it looks like:** independent
  steps (e.g. semantic/group/cnd don't depend on localize) keep running after a sibling
  fails; the run only fails when the failed step exhausts retries AND a dependent needs
  it. Read per-step `verification.errors`, not just the run status.
- **`gate_type` inference matches step id+title ONLY** — acceptance criteria embed
  project paths, and a project named `contentful` turned every halted gate into a
  "content" panel (substring poisoning). Keep broad keywords away from criteria text.
  Known gate types: `deploy` (deploy/build_deploy), `groundtruth` (ground-truth /
  live-fidelity), `fidelity`, `mirror`, `model`, `golive`, `content`, `scope`.
- **Persisted "running" is a lie after an engine restart** — `load_run` and the runs
  list normalize it to `paused` (no loop exists). In-memory status wins when a loop is
  registered.

See the fixed pipeline + gates in [`../orchestration/ANALYZE-PIPELINE.md`](../orchestration/ANALYZE-PIPELINE.md)
and the cockpit UI in [`frontend/MIGRATION_PROFILE.md`](frontend/MIGRATION_PROFILE.md).
