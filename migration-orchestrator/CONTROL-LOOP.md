# Driving a migration from an LLM — the control-loop contract

> **The cockpit web UI is observability-only.** Runs are launched and relaunched
> **exclusively by an LLM/agent via this REST API** — `POST /migrations`,
> `/runs/{id}/start`, `/runs/{id}/restart`, the epic/story restart routes, and
> `/runs/{id}/jump` have **no UI control** any more. The web UI observes (run list,
> detail, progress tree, logs, quality panels, artifacts) and still exposes the
> in-flight **decision** surfaces (pause / resume / abort and the gate
> approve / reject / rerun panels) — but never launch or restart.

The migration cockpit is drivable by an LLM/agent over the REST API below, and
**observable** by a human through the web UI. This is the poll→decide→act contract
an agent follows. The engine stays the dumb executor; the agent is the brain that
reads quality signals and decides whether to advance, escalate to a human, or roll back.

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
| `GET` | `/runs/{id}/decisions` | pending **decision bundles** (attempts, failure_context, strategies remaining/applied, probe + Run: command stdout/stderr tails, inputs, next_actions) |
| `POST` | `/runs/{id}/steps/{step_id}/decide` | `{action, reason, strategy_id?, rules?, rules_file?, patch?, rerun_from?, step_id?, inputs?}` — typed, **audited** decision (`action`: `apply_and_rerun` \| `proceed` \| `retry` \| `repatch`) |
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
- `POST /runs/{id}/resume` with a `halted`, `rejected` or `decision_pending` step
  present is refused: the run stays paused and the engine logs which step blocks it
  and what to do (approve/reject via the gate endpoint, decide via the decide
  endpoint, or jump/rollback). Resuming is never a silent approval.

## Decision points (ASSIST-PLAN §3) — `decision_pending` + `/decide`

A step reaches **`decision_pending`** (run → `paused`, persisted, survives engine
restarts) in three cases (P5.5b — DeepSeek is out of the control loop, so there is
no repair-agent fallback; a stuck step ALWAYS becomes a decision, never a silent
run failure):

1. **Retries exhausted — with OR without strategies.** `attempt` is a 1-based
   execution counter and `max_attempts` the total budget; when the budget is spent
   the step parks as `decision_pending` and the run pauses, whether or not the step
   carries unconsumed `strategies`. The decision bundle carries the stashed
   `failure_context` (failed `Run:` command, exit code, stderr/stdout tails, or the
   verification errors).
2. **Review steps** (`review: true`, e.g. `step_model_review`): scheduled
   checkpoints the engine NEVER sends to an agent — selection = `decision_pending`.
   Review steps are exempt from the deploy/content PROBE plan lint.
3. **Epic gate not green** (`epic_gate_not_green`): epic approval is deterministic
   (all steps done + all verifications passing → approved; the LLM reviewer is
   gone). When every story is approved but a step is done with a red verification,
   the epic loop parks that step; once decided, it re-enters, re-executes and
   re-judges the epic.

`GET /runs/{id}/decisions` returns the decision bundle per pending step: `reason`
(`retries_exhausted` | `review`), attempts, `failure_context`, strategies
remaining/applied, last verification errors + probe AND engine-run `Run:` command
stdout/stderr tails (from the audit trail), step inputs, `next_actions`, and the
derived default scope-rules file. `status.gate` shows
`{type: "decision", step_id, summary}` with
`next_actions: ["decide", "rollback", "restart"]`.

`POST /runs/{id}/steps/{step_id}/decide` — the ONLY way out of `decision_pending`:

```jsonc
{
  "action": "apply_and_rerun",       // or "proceed" | "retry" | "repatch"
  "reason": "stability RED 0.733; widen the estimator",  // required, audited (alias: rationale)
  "strategy_id": "consensus3",      // apply_and_rerun: pre-registered on the step (single-shot)
  "rules": [{"id": "exclude-consent-banner", "action": "exclude",
             "match": {"selector": "#onetrust-banner-sdk"}, "scope": "site",
             "reason": "…", "decidedBy": "claude", "date": "2026-07-03"}],
  "rules_file": null,                // default: <projects/X>/workflow-output/scope-rules.json
  "patch": null,                     // apply_and_rerun free-form — autonomy=manual (Julian) ONLY
  "rerun_from": null,                // default: the decided step (arm swap: the patched arm)
  "step_id": null,                   // repatch: target step (default: the decided step)
  "inputs": null                     // repatch: inputs to MERGE into the target step
}
```

- **`retry {reason}`** re-queues the decided step UNCHANGED with a fresh attempt
  budget (attempts reset, `failure_context` cleared) via the jump machinery. No
  strategy/patch/rules allowed — it is the "the world was fixed out of band, run
  it again" action.
- **`repatch {step_id?, inputs, reason}`** (U4, amendment 4b) MERGES `inputs` into
  the target step (default: the decided step), clears its `failure_context`,
  resets attempts and reruns. **Inputs ONLY**: `acceptance_criteria` (and its
  `PROBE:` lines) are frozen bars — any field beyond `inputs` in the request is
  refused (extra-field tripwire, rule 1). Allowed in ANY autonomy (it cannot move
  a bar). A repatch targeting ANOTHER step also re-queues the decided step as
  `pending` so nothing stays parked.
- **`strategy_id`** (apply_and_rerun) applies the strategy's `patches` (full
  replacement of the provided fields on each target step) and `skip` list (steps
  marked done without execution), then resets + reruns via the jump machinery
  (dependents reset). A `halt: true` strategy (manual_review) converts the
  decision into a `halted` gate (`gate_type: "segmentation"`) for Julian instead.
- **`rules`** are appended (deduped by id) to the project's `scope-rules.json`
  whatever the action — pattern-keyed only (`selector`/`signature`, never a page
  URL). Emitting rules with no strategy reruns the decided step against them.
- **Frozen bars never move:** the plan lint refuses any non-`arm_swap` strategy
  patch that drops/modifies a `PROBE:` line of its target step, `/decide` refuses
  free-form patches that do (free-form patches additionally require
  `autonomy: "manual"`), and `repatch` refuses anything but `inputs` outright.
- Every decision lands in the event log as a `decision` event (action, strategy,
  patch, repatch before/after + keys_changed, rules, rationale) — same audit
  contract as `gate_decision`.

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
- **Retries actually retry (fixed 2026-07-03).** The old retry branch re-queued a
  failed step as `ready`, which `select_next_ready_step` never picks — every step
  silently got ZERO retries (P4: step_segment died at attempt 1/3). Failed steps
  now re-queue as `pending`; the same fix applies to answered `waiting_human`
  steps, and the human answer is now injected into the rebuilt prompt
  ("Réponse humaine à ta question précédente: …").
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
- **Integrity belt (plan-independent completeness, added 2026-07-04).** Per-step probes
  are gates — they only assert what one step promised, and a *weak* one can pass over a
  hollow site (observed live: a `content.get` on `/home` alone went green with 0/19
  sub-pages created). The belt closes that blind spot: after a **content** step
  (`task_type == "content"`, or the ids `step_pages` / `step_content_load` /
  `step_publish_parity`) passes its own probes, `verifier.run_integrity_belt` runs
  `orchestration/probes/integrity.py <project> <site> --phase <step_id>` as an
  **additional** verification. That probe is read-only: it derives EXPECTATIONS
  mechanically from the pipeline artifacts (page tree from `page-inventory.json`,
  per-page instance counts from `content/<project>.content-load.json`, media from
  `images/<project>.dam.json`) and diffs them against the live Jahia over GraphQL
  (EDIT, and LIVE where the phase expects publication), exiting non-zero on any
  mismatch (a page missing, a page that expects content but has an empty main area, or
  media/instance drift below `--min-ratio`). A non-zero exit **fails the verification**
  and takes the same retry/decision path as any probe — it is audited like a probe with
  an `[integrity]` marker in the command. Site key comes from `inputs.site` (now emitted
  by `gen_plan`), falling back to the project basename so in-flight plans that predate
  the field still work; with no project/site derivable it **skips gracefully** with an
  audit note, never crashes. Kill-switch: `ORCHESTRATOR_INTEGRITY=false` (default on);
  own timeout `ORCHESTRATOR_INTEGRITY_TIMEOUT` (default 120s).

See the fixed pipeline + gates in [`../orchestration/ANALYZE-PIPELINE.md`](../orchestration/ANALYZE-PIPELINE.md)
and the cockpit UI in [`frontend/MIGRATION_PROFILE.md`](frontend/MIGRATION_PROFILE.md).
