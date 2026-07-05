# WORKFLOW-IMPROVEMENTS — generic reliability, orchestrator UX, assistant actionability

Proposed 2026-07-04, after the discoverasr modular re-migration (P6). **Every item is
anchored in a REAL friction observed this session — none speculative. That anchoring IS the
anti-overfit discipline: we harden what actually broke, generically.**

---

## Category 1 — Generic workflow reliability (no overfit)

### 1.1 Uniform EDIT-only publish guard (shared, not per-script)
- **Friction:** `create_pages.py` published 20 page shells while `load_content.py` was made
  EDIT-only — the doctrine was applied ad-hoc, script by script.
- **Fix:** one shared guard (`PROCESS_EDIT_ONLY=1` env honored by `mcp_client.publish`, which
  becomes a no-op + audit line during the process). Publication happens ONLY in the final
  `publish_site.sh`. Any future mutating script inherits it for free.
- Effort: low · Impact: high (kills the whole doctrine-drift class).

### 1.2 Strict end-of-phase reality belts everywhere (A1, generalized)
- **Friction:** a silent LIVE-purge abort left 925 stale uuids; G2 went red 3 gates later.
- **Fix:** every phase self-checks against Jahia reality at its boundary and fails fast —
  not 3 gates downstream. Done for `content_load`/`publish_parity`; extend to `create_pages`
  (assert N pages exist), `create_site` (home/files/groups/langs), `deploy` (types ACTIVE).
- Effort: medium · Impact: high.

### 1.3 Reconcile-and-resume as a universal step contract (A2, generalized)
- **Friction:** an OOM/interrupt nearly restarted from 0; a site-recreate did NOT chain
  `create_pages`, so the loader hit "parent path does not exist" on all 19 child pages.
- **Fix:** generalize the ledger + JCR-reality verdict (ALIGNED / REBUILD) to every mutating
  step; make each step verify its OWN preconditions exist (load ⇒ pages exist ⇒ site exists)
  and self-heal the missing upstream. Incidents then cost only the broken slice.
- Effort: medium · Impact: high.

### 1.4 "Operation successful ≠ done" — a verify-against-reality primitive
- **Friction:** deploy returns `{}` on success AND failure; `publish` no-ops in 1 ms on
  corrupted metadata; `createSite` silently ignores `languages`.
- **Fix:** a shared `verify_reality(assertion)` helper; every mutation is followed by a
  reality assertion (types ACTIVE / node exists / uuid aligned / langs set). Turns per-caller
  boilerplate into one call.
- Effort: low-medium · Impact: high.

### 1.5 Fidelity-safe recognizer registry + fallback-always (the anti-overfit core)
- **Friction:** the whole P6 arc — the model must get modular WITHOUT losing fidelity.
- **Fix:** the recognizers (logoWall/carousel/tabs) live in a registry; each PROVES itself
  pixel-safe (scoped-zone compare) or falls back to verbatim `rawHtml`. The pipeline degrades
  gracefully to verbatim, never blocks, and every promotion is gated by fidelity — not by a
  heuristic that could overfit one site.
- Effort: ongoing · Impact: high (generalizes to any site).

### 1.6 Library-gap telemetry → data-driven library growth (kills overfit-by-guessing)
- **Friction:** I *guessed* "carousel is the biggest gap"; the composability probe + fallback
  log PROVED it (72/141 frozen sections were JS widgets).
- **Fix:** every rawHtml fallback logs its pattern signature; a cross-site report ranks the
  gaps by frequency → build the next recognizer by DATA, not intuition.
- Effort: low · Impact: high.

### 1.7 Capture-faithfulness contract (consolidate existing invariants)
- **Friction:** charset mojibake (rule 20), post-hydration render (rule 30), lazy-image
  materialization (30b), cloned-slide dedup (P6.3-bis) — each was learned the hard way.
- **Fix:** a single "capture contract" checklist any new site runs through before recompose.
- Effort: low · Impact: medium.

---

## Category 2 — Orchestrator UX

### 2.1 Decision-bundle UI that renders the WHY
Every `decision_pending` shows the failing command (exit code + stderr tail), the per-page
probe results, and the **visual diff (ref/live/diff PNG) inline**. *Friction:* I had to curl
+ open PNGs by hand to diagnose the ground-truth ceiling.

### 2.2 Reality-derived progress (belt ticks), not step status
Per-phase progress from Jahia reality (nodes created/expected, uuid alignment), not just
"running". Julian's standing 5-min directive already wants this — make it first-class.

### 2.3 Composability + fidelity dashboard per project
Ratio, over-K types, monoliths, library gaps, fidelity-per-page — the P6 gates visualized,
with a before/after across runs.

### 2.4 Run comparison / diff
Diff two runs (before/after a recognizer or fix): composability delta, fidelity delta, node
counts. *Friction:* I manually compared plan-vs-reality and run-vs-run repeatedly.

### 2.5 Library-coverage view
Which patterns are promoted vs fallback, per site — "how modular is this migration" at a
glance.

---

## Category 3 — Observability & actionability FOR THE ASSISTANT (leverage, not doing all the work)

### 3.1 Structured, queryable signals (not log-parsing)
The orchestrator exposes, per step, the decision bundle + probe outputs + artifact pointers
via ONE API call — so I gather conclusions, not file dumps. *Friction:* I hand-rolled dozens
of curl+python GraphQL parses this session.

### 3.2 The self-gating agent contract, formalized
Agents self-gate on OBJECTIVE criteria (composability jump, fidelity, clean spot-checks) and
STOP+report at real forks — never thrash. Proven repeatedly this session (P6.3 self-gate
correctly stopped at 13.2%). Make it the standard subagent brief template. **This is the
core "without doing all the work" lever:** I delegate big work and only spend judgment at
genuine bifurcations.

### 3.3 A decision-queue surfaced to me
The engine presents exactly the decisions needing judgment (decision_pending + pre-digested
bundle). My tokens go to decisions, not investigation — the P5 charter (engine executes, I
decide at points) made operational.

### 3.4 Cheap-tier pre-triage (P5.6 DeepSeek), extended
DeepSeek pre-digests each decision bundle + proposes a default action; I confirm rather than
derive. Extend to: pre-classify fidelity failures (real defect vs rule-35 metric noise),
pre-rank library gaps.

### 3.5 Telemetry that tells me WHERE to invest
The library-gap log (which recognizer next), the fidelity-drift breakdown (real vs noise),
composability-per-site (which site tests the thesis). *Friction:* the composability probe
redirected me from "push more recognizers on discoverasr" to "discoverasr is the worst case,
prove the thesis on a card-heavy site."

### 3.6 A verify-against-reality primitive I invoke
"Is EDIT what the plan says?" / "Is this node editable (forms.editForm)?" / "Are EDIT/LIVE
aligned?" — one call each, instead of hand-rolling GraphQL. Turns the reality-checks I ran
repeatedly into one-liners.

### 3.7 Replayable audit trail
Every mutation/decision is audited (already). Add "reconstruct state at step N" so I never
re-investigate; the run's history is queryable.

---

## Suggested sequencing (highest impact / lowest effort first)
1. **1.1 publish guard** + **1.4 verify-reality primitive** + **3.6** (same primitive) — low
   effort, kills the doctrine-drift + "operation successful" failure classes.
2. **1.6 library-gap telemetry** + **3.5** — cheap, and it directs all subsequent P6 effort
   by data (anti-overfit).
3. **3.2 self-gating agent contract** — a template, near-zero cost, biggest leverage on my
   time.
4. **1.3 reconcile-everywhere** + **1.2 belts-everywhere** — medium effort, ends incident
   restart-from-0.
5. **2.x cockpit** — as the engine's decision-queue (3.3) matures.
