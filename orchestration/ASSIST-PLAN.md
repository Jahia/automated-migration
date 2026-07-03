# ASSIST-PLAN — P5: engine-driven, LLM-assisted migration

**Registered: 2026-07-03, BEFORE implementation and before any protocol-v2 measurement.**
Governing doc: `QUALITY-PLAN.md` (pre-registration clause applies: thresholds and protocols below
may only change with a dated amendment, never retroactively to make a run pass).

**Goal:** invert the control relationship. The committed workflow orchestrator
(`migration-orchestrator/`, FastAPI :8001 → opencode :4096 → DeepSeek V4 Flash agents +
Qwen2.5-VL at OVH for vision) OWNS execution: plans, agents, probes, gates, retries. The LLM
assistant (Claude) becomes a STRATEGIST invoked only at decision points, with the observability
and entry points to (a) choose between pre-registered strategies (heuristic fallback? sample a
cluster on 3 pages? A/B two arms? manual review?) and (b) emit generalized SCOPE RULES ("exclude
the cookie banner from the reconstruction", §5). Decisions are confined to the calibration
phase and generalized as pattern-keyed rules, so the remaining 30–10,000 pages are processed by
the orchestrator alone. End state of this plan: **the discoverasr (Ascott,
https://www.discoverasr.com/en) 20-page migration runs under the engine to completion.**

---

## 0. Mode definition & rules of engagement (FROZEN)

Autonomy ladder (existing `autonomy` field, `src/routes/runs.py:246`):

| Level | Gates (HALT) | Decision points | Free-form step patches |
|---|---|---|---|
| `manual` | Julian | Julian | Julian |
| `assisted` (default) | assistant approves GREEN only; RED/amber → Julian | assistant picks from the step's registered strategy list | forbidden |
| `autonomous` (future) | auto-approve green | engine picks strategies in declared order | forbidden |

Rules:

1. **Frozen bars never move** (stability 0.8, coverage 50, G1 60/85, reconstruct 95,
   ground-truth 99). Strategies change **how evidence is gathered**, never the bar. Enforced
   structurally: gate thresholds live inside probe code (e.g. `segment_probe.mjs:211,225`), and
   the decide endpoint refuses any patch that touches a `PROBE:` line unless the patch is a
   whole pre-registered arm swap emitted by `gen_plan.py`.
2. **The assistant may approve a HALT gate iff its probe verdict is GREEN** (checkpoint ack —
   same role as the P3/P4 sessions). RED or amber → Julian. CONTROL-LOOP's "never approve a red
   gate" stands.
3. **Every steering action goes through the audited API** (`/gate`, `/decide`, `/rollback`, all
   with `reason`). Zero out-of-band actions (shell edits of run state, mid-run file fixes, code
   changes). **Amendment to P4's "zero manual interventions" (dated 2026-07-03, pre-measurement
   for the 20-page run):** audited protocol decisions are part of the system; out-of-band
   actions remain interventions and void the run (fix, record, restart).
4. One rollback per failure class, then escalate (CONTROL-LOOP.md kept).
5. **Honest-outcome clause:** "run to completion" includes a documented red verdict with
   evidence. A run that ends in a Julian-reviewed rejection has still been taken to the end.
6. **Intervention confinement & generalization invariant.** The assistant acts ONLY at
   decision points, and decision points exist only in the CALIBRATION phase (analyze epics on
   the representative sample) plus two scheduled reviews (model review, end-of-batch exceptions
   review — §3 A6). Every decision is expressed as a **site-level rule keyed on a pattern**
   (CSS selector, component signature, cluster id) — never on a page URL; `/decide` lints
   this, and page-scoped rules require `manual` (Julian). The BATCH phase (the remaining
   30–10,000 pages) is orchestrator-only: a page that does not fit the frozen profile is
   queued into an exceptions report, never escalated to the assistant mid-batch. The monitor
   does not wake the assistant on batch step transitions — only on decision points, gates,
   and terminal states.

---

## 1. What exists (verified by recon, 2026-07-03)

The engine already has most of the LLM control surface (`CONTROL-LOOP.md`;
`src/routes/runs.py`):

- `GET /runs/{id}/status` — compact status with `gate`, `quality.verdict`, `next_actions`
  (`migration_control.py:198-239`); `GET /runs/{id}/log?since=` cursor tail; `GET /quality`;
  SSE `/events`; audit JSONL `/runs/{id}/audit` (`/tmp/orch-audit/{run}.jsonl`); SQLite
  `orchestrator.db` (full RunState + events).
- `POST /runs/{id}/gate {approve|reject|rerun, reason}` — audited; approve is the ONLY
  halted→done path; resume with a halted/rejected step is refused (`orchestrator.py:841-846`).
- `POST /runs/{id}/rollback {to_step, reason}` / `/jump` — reset + re-run, **with identical
  step params** (no re-parameterization exists).
- Retry: `attempt < max_attempts` → re-run (`orchestrator.py:301-306`); exhausted → story →
  epic → run `failed`, `next_actions: [rollback, restart]`.
- PROBE lines are engine-enforced ground truth (`verifier.py:94-176`) — proven live on P4:
  the DeepSeek agent REPORTED "stability 1.0 GREEN" for step_segment, the engine's own probe
  re-run said RED 0.733 (run_1783106607306 state_json). The agent is never trusted on gates.
- Segmentation facts: cluster rep = `c.pages[0]` only (`segment_probe.mjs:48-56`); stability =
  2 runs + conditional 3rd, best-pair Jaccard ≥ 0.8 hardcoded (`:206-226`); no per-cluster
  sampling flag, no upfront-N consensus, no A/B harness (P2's A/B was two manual plan runs).
  `segment2manifest.py` already merges multi-page segmentations by normalized component name.
- discoverasr state: 21 pages render-crawled + localized in
  `projects/discoverasr/workflow-output/local-mirror/`; mirror gate PASS (8/8); ONE template
  cluster; only `en` segmented (agreement 0.733, coverage 68%, 14 components); **no site, no
  module, nothing past epic_analyze step 5/24**. The plan at git HEAD is the 20-page version
  (working tree downgraded it to 8 for the P4 attempt).

## 2. Gaps this plan closes

- **G-A — no step re-parameterization:** jump/rollback re-run identical params; no endpoint
  edits `inputs`/`acceptance_criteria` (`recon §5`). "Retry with 3-page sampling" is impossible.
- **G-B — no decision-point concept:** retries exhausted → run `failed`; the operator gets
  `[rollback, restart]`, both of which repeat the same failure.
- **G-C — no strategy library:** per-cluster k-sampling, upfront N=3 consensus, A/B harness,
  runtime arm swap — none exist as invocable options.
- **G-D — `human_answer` never reaches the agent:** `POST /steps/{id}/answer` stores the answer
  but `prompt_builder.py` never injects it — the step just re-executes blind.
- **G-E — observability holes:** OVH vision calls not cost-tracked; `cost_tracker.py:57`
  relative path nests `migration-orchestrator/migration-orchestrator/costs/`.
- **G-F — secrets:** the OVH JWT was captured verbatim in `events.payload_json` streaming
  deltas (orchestrator.db) when the agent grepped `~/.config/opencode/opencode.jsonc`.

---

## 3. Phase A — decision-point protocol (engine)

**A1. Schema.** `Step.strategies?: Strategy[]` (backwards compatible — absent = today's
behavior). `Strategy = {id, title, when: "on_retries_exhausted", order, patches:
[{step_id, inputs?, acceptance_criteria?}], skip?: [step_id], notes}`. Strategies are DATA
emitted by `gen_plan.py` — pre-registered by construction.

**A2. New state.** On retries exhausted **with strategies remaining**: step →
`decision_pending` (new StepStatus), run → `paused` (not `failed`). `compact_status.gate =
{active, type: "decision", step_id, strategies: [...applied/remaining...]}`, `next_actions:
["decide", "rollback", "restart"]`. `GET /runs/{id}/decisions` returns the full decision
bundle: attempts history, probe stdout/stderr, parsed gate metrics (e.g. `segment-check.json`),
artifact links (`/runs/{id}/artifacts/segment/en.segmap.html`, screenshots) so a multimodal
assistant can LOOK at the segmentation overlay before choosing.

**A3. Decide endpoint.** `POST /runs/{id}/steps/{step_id}/decide {strategy_id? , rules?[],
action: apply_and_rerun|proceed, rationale}` (assisted) or `{patch, rationale}` (manual/Julian
only). `strategy_id` applies the strategy's patches (multi-step — an arm swap patches
`step_group` and skips `step_segment`); `rules` appends generalized scope rules (§5) to the
run's rule set; both reset attempts, force the step next, resume the loop. Audited as a
`decision` event (strategy, rules, patch diff, rationale). Each strategy is single-shot: once
applied it leaves the remaining list. Strategies exhausted + still RED → run `failed` as
today (escalate to Julian).

**A4. Fix `human_answer` injection** into the rebuilt prompt (`prompt_builder.py`) — the
question/answer channel becomes a usable context-repair tool.

**A5. Integrity.** decision_pending survives engine restart (persisted like halted/rejected);
plan lint extended: strategy patches may not modify `PROBE:` lines unless the strategy is
flagged `arm_swap` (generator-emitted); frozen-threshold literals never appear in patches.

**A6. Scheduled decision points (not only failure-triggered).** Two review checkpoints are
emitted by `gen_plan.py` using the same `decision_pending` machinery, reached ALWAYS (not only
on RED):
- **`step_model_review`** (after `step_group`, before extraction): the assistant reviews the
  component manifest + segmentation overlays and may emit scope rules (§5) — e.g. "exclude
  the consent banner site-wide" — or `proceed`. This is migration rule 21 ("judge the model
  editorially at the model gate") made a first-class, audited checkpoint.
- **`step_exceptions_review`** (end of the batch phase): reviews the exceptions report (pages
  that didn't fit the frozen profile), generalizes new rules if warranted, and triggers a
  re-run of ONLY the exception pages. One checkpoint for the whole batch — never per page.

**A7. Two-phase run topology: CALIBRATE → BATCH.** Calibration = the analyze epics on the
representative sample (cluster reps, k pages per cluster) — all strategy decisions, scope
rules, and model review happen here; its output is a **frozen migration profile** (component
manifest + CND + scope-rules file). Batch = every remaining page processed by the orchestrator
alone applying the frozen profile (extract → load → publish → per-page probes); batch steps
carry `strategies: []` and queue misfits to the exceptions report. For M4 (20 pages) the
existing epic granularity already maps onto this (epic_analyze = calibration, epic_content =
batch); at 30–10,000 pages the batch becomes chunked page-group steps — design holds, chunked
implementation is beyond M4 (§11).

## 4. Phase B — strategy library (segmentation first)

**B1. `segment_probe.mjs`:** `--per-cluster k` (sample `c.pages.slice(0,k)` instead of `[0]`,
at `:48-56`) and `--consensus` (upfront N gated runs — reuse `--stability N` flag; agreement =
MEAN pairwise Jaccard of root-sets; consensus root-set = ids in ≥⌈N/2⌉ runs; emitted
segmentation = the run closest to consensus, annotated with `consensus:true`). Incremental:
skip pages that already have a passing `*.segmentation.json` (retry- and resume-friendly).
Gate semantics: protocol v2 (§7). Scope rules (§5) are applied to the DOM before the pass.

**B2. `segment2manifest.py`:** cluster-aware merge — only PASSING pages feed the manifest
(cross-page name aggregation already exists, docstring `:2-26`).

**B3. `ab_segment.sh` (new):** run BOTH arms on the same frozen mirror — vision
(`segment_probe` + `segment2manifest`) vs heuristic (`group_llm.py` + `assemble_manifest.py`)
— into separate output dirs, judged by `reconstruct_probe.mjs` fidelity proxy + partition
coverage on the sampled pages; emit `ab-report.json`. This is an **information strategy**: its
outcome feeds the next decision (`keep_vision` re-roll vs `heuristic_arm`), pre-registered
judge, same pattern as P2's A/B.

**B4. `gen_plan.py`:** `--per-cluster` flag passthrough; emit on `step_segment` the ordered
strategy list `[consensus3, sample3, claude_adjudicate, ab_test, heuristic_arm,
manual_review]` where `heuristic_arm` is the generator's own arm-swap patch (both arms
already share the `step_group` id by design, `gen_plan.py:61-79`); emit the two scheduled
review checkpoints (`step_model_review`, `step_exceptions_review`, §3 A6).

**B5. `manual_review`:** converts the decision into `halted` with `gate_type: "segmentation"`
and a review bundle (segmap overlays, consensus diff). A human override of a red segmentation
gate is **Julian's prerogative only**, recorded as a waiver in the audit trail and in
QUALITY-PLAN's log.

**B6. `claude_adjudicate`** *(same-day pre-measurement amendment, 2026-07-03, on Julian's
direction: "on utilise ta vision et ta réflexion pour trancher et aider à aller vers du
vert")*: when protocol v2 stays RED on a cluster, the assistant (multimodal) reviews the rep
pages' screenshots + the N gated segmentation overlays and ADJUDICATES a component set per
page — selecting one run or synthesizing a root-set from the outline's REAL block ids
(hallucination-impossible: ids validated against the outline, exactly like gated runs;
coverage ≥ 50 still applies). Ingested by `adjudicate_ingest.mjs`, which validates and writes
`<slug>.segmentation.json` flagged `{adjudicated: true, adjudicator, rationale}`.
**Gate semantics:** the page is **GREEN-BY-ADJUDICATION**, recorded distinctly from
GREEN-by-stability in `segment-check.json` and the log — the stability bar is never silently
waived; the nondeterministic-generator risk it guards against is answered by a recorded,
audited judge pick instead, and the adjudicated model must still clear every downstream
deterministic gate (partition, recompose, fidelity, G1/G5/G6/G2, ground truth). Confinement
intact: adjudication happens at a decision point, applies cluster-wide, batch untouched.
**Strategy order becomes** `[consensus3, sample3, claude_adjudicate, ab_test, heuristic_arm,
manual_review]` — assistant adjudication is tried before sacrificing fidelity to the
heuristic arm.

## 5. Scope rules — editorial decisions as generalized data (second decision type)

Strategy decisions (§4) change **how evidence is gathered**. Scope rules change **what is in
the migration** — the "I don't want the cookie banner in the reconstruction" class of
decisions. They are DATA, applied deterministically by the pipeline, which is what makes the
batch phase LLM-free.

**Schema.** `projects/<p>/workflow-output/scope-rules.json` (committed at consolidation, like
the DAM dedupe maps): each rule
`{id, action: exclude | force_passthrough, match: {selector | signature}, scope: site |
cluster:<id>, reason, decidedBy, date}`.
- `exclude`: the region is NOT migrated at all (consent banners, chat widgets, promo
  interstitials).
- `force_passthrough`: the region IS migrated but verbatim (`rawHtml`), never componentized —
  for busy widgets that destabilize segmentation but must ship.
- `match` is a pattern (CSS selector or component signature) — **never a page URL** (§0
  rule 6). `scope` defaults to `site`.

**Effects — every consumer honors the same file:**
1. **Canonical application point:** the SCOPED DOM = mirror ∖ excluded regions, derived once
   per run, deterministically. All downstream contracts (recompose byte-identity, rule 23;
   partition; skeletons) are defined against the scoped DOM, so exclusion never breaks the
   self-checks.
2. **Segmentation** (`segment_probe.mjs`): excluded regions pruned BEFORE the outline/vision
   pass — decluttering is a legitimate evidence change (bar unchanged), and on discoverasr the
   consent banner is one of the named instability drivers.
3. **Partition gate:** excluded regions become a third leaf category `excluded-by-rule` —
   exactly-once accounting is preserved, no silent holes.
4. **G1 contribution:** excluded zones leave the denominator (extends migration rule 29's
   widget exclusion).
5. **Pixel gates** (`reconstruct_probe`, `groundtruth.sh`): masks auto-derived from rule
   selectors at render time, applied to BOTH sides — this extends the existing committed
   `groundtruth-masks.json` policy (reason required, QUALITY-PLAN masking clause).
6. **Content load:** excluded regions are stripped from skeletons/rawHtml — the migrated site
   genuinely does not ship the banner.

**Honesty caps (pre-registered):** every rule carries a reason and appears in the run report +
QUALITY-PLAN log; the excluded pixel share is REPORTED per page; any page whose excluded share
exceeds **20% of the rendered area** is flagged for Julian review (a review trigger, not a
gate). Exclusion is an editorial scope decision — it must never become a way to hide fidelity
failures of migrated content, so only rules declared BEFORE reconstruction generate masks.

**Where rules are emitted:** at any decision point — failure-triggered (e.g. segmentation RED
→ `exclude` the banner, then re-run) or scheduled (`step_model_review`, `step_exceptions_review`,
§3 A6). Implementation: one shared library (`orchestration/lib/scope_rules.py` + a thin .mjs
twin) consumed by segment/extract/partition/reconstruct/groundtruth/loader.

## 6. Phase C — observability & hardening

- **C1.** Decision bundle artifact links (A2) — includes the rep pages' `*.segmap.html` and
  `*.page.png` so decisions are made on evidence, not just numbers.
- **C2.** Vision cost/latency logging: `ovh_vision.mjs` appends per-call usage to
  `workflow-output/segment/vision-usage.jsonl`; cost report merges it (today vision is
  invisible in `costs/run_*.json`).
- **C3.** Fix `cost_tracker.py:57` to an absolute path (kills the nested
  `migration-orchestrator/migration-orchestrator/` artifact).
- **C4. SECURITY:** redaction filter (known provider-key regexes) applied to streaming deltas
  and audit payloads BEFORE persistence; agent prompts forbid reading
  `~/.config/opencode/opencode.jsonc`; scrub existing `orchestrator.db` events; **rotate the
  OVH key** (it sits verbatim in the DB today). Tracked as an independent task.

## 7. FROZEN measurement protocol v2 — segmentation stability (pre-registered)

Registered BEFORE any v2 measurement. The BAR does not move; the ESTIMATOR does.

- **Per page:** N=3 upfront gated runs; page agreement = **mean pairwise Jaccard** of
  component root-sets; page PASS iff agreement ≥ **0.8** AND coverage ≥ **50** (both unchanged).
  Note honestly: mean-pairwise is *stricter* than the old best-pair on a single page.
- **Per cluster:** sample **k = min(3, |cluster|)** pages (cluster order); cluster PASS iff a
  strict majority of sampled pages pass (k=3 → ≥2; k=2 → 2; k=1 → 1).
- **Gate GREEN iff every cluster passes.** Manifest = cross-page merge of passing pages.
- **Rationale:** P4's verdict rested entirely on ONE page (`en`) of one cluster — maximal
  variance. v2 reduces estimator variance without touching the 0.8 bar.
- **Scope-rule interaction:** stability is measured on the SCOPED DOM (§5) — excluding a
  consent banner declutters the input identically on every page (pattern-keyed), which is an
  evidence change, not a bar change. Rules in force at measurement time are listed in
  `segment-check.json`.
- **Adjudication clause** (registered same-day, pre-measurement): a page may be
  GREEN-BY-ADJUDICATION (§4 B6) — recorded distinctly, and protocol v2's stability numbers are
  STILL measured and reported for every page. The estimator is never silently bypassed.
- **Holdout honesty:** discoverasr's pristine-holdout status is SPENT (0.733 is known). It now
  becomes the development case for the decision protocol; **protocol v2's own holdout is the
  next unseen site.** Any protocol tweak after the first v2 measurement requires Julian + a
  dated amendment here.

## 8. Phase D — the assistant operating loop

- **D1.** `orchestration/assist/monitor.sh` (committed version of the proven session poller):
  polls `/status` + `/log?since=cursor`, prints transitions, exits on
  `gate|decision_pending|terminal` — run in background by the Claude session, which wakes on
  events.
- **D2.** On wake: read the decision bundle (metrics + overlays), decide via API with a
  written rationale, log the decision. End of run: append the outcome to QUALITY-PLAN's
  execution log (append-only, as always).
- **D3.** Escalation to Julian: strategies exhausted; red/amber HALT gate; any destructive
  next-action (site deletion, license juggling); anything not on a registered list.

---

## 9. Milestones

- **M0 — this doc registered** (cross-linked from QUALITY-PLAN §log).
- **M1 — strategy + scope tooling offline** on the CACHED discoverasr mirror (21 local pages):
  `--consensus`, `--per-cluster`, `ab_segment.sh`, and `scope_rules` application run
  end-to-end offline; self-checks pass (recompose byte-identity against the scoped DOM). The
  demo case: `exclude` the discoverasr consent banner → re-run segmentation → record the
  stability effect. Numbers recorded as engineering evidence — NOT the graded run (freeze
  precedes measurement; no protocol change between M1 and M4 without Julian).
- **M2 — engine decision smoke** on a synthetic 3-step plan with a forced-RED step + 2
  strategies + a scheduled review step: `decision_pending` reached → `/decide` applies a
  strategy patch AND a scope rule → re-run passes → audit shows both decisions →
  engine-restart preserves the state. ALSO settle two engine questions:
  (a) retry-on-verification-failure semantics (P4's DB shows step_segment `failed` at
  `attempt: 1` of 3 — the "retried 3×" account must be confirmed or the retry path fixed);
  (b) the 600s step-completion deadline vs long segment runs (protocol v2 worst case ≈ 3
  clusters × 3 pages × 3 vision runs ≈ 27 gated calls ≫ 600s) — choose: run segmentation as
  `PROBE[2700]` (engine-executed, per-probe timeout exists), split per cluster, or raise the
  deadline. Must be decided and tested HERE, not discovered in M4.
- **M3 — full-loop rehearsal on acquia (recommended, Julian may skip):** the full 24-step plan
  engine-driven on the known-good site — the engine has NEVER traversed deploy/content/G-gates
  end-to-end (P4 died at step 5/24). Closes QUALITY-PLAN next-step #1. Recreates the acquia
  site in place. Skipping saves a run but means M4 debuts the engine on those phases on an
  unseen site.
- **M4 — THE RUN: discoverasr, 20 pages, engine-driven, LLM-assisted, to the end.**
  Regenerate the plan (`gen_plan.py --max-pages 20 --per-cluster 3` + strategies; HEAD already
  carries `--max-pages 20`; 21 pages already crawled+localized so analyze re-runs are cheap).
  Expected shape: crawl(20, cache) → localize → mirror gate → semantic (20 pages will likely
  split into SEVERAL clusters — destinations/properties/contact/policy — which alone improves
  the stability base) → segment under protocol v2 (if RED: decisions in order consensus3 →
  sample3 → claude_adjudicate → ab_test → heuristic_arm/manual_review) → group → extract (G1/G5) → cnd → fidelity
  HALT → module epics → deploy gate → site+content (license watch) → G6/G2 → ground-truth HALT
  (≥99/page vs the frozen mirror).
  **Acceptance:** run status `completed` (or a Julian-reviewed documented rejection — §0
  rule 5); every steering action present in the audit trail; zero out-of-band interventions;
  **confinement auditable** — every assistant decision timestamp falls inside the calibration
  window or a scheduled review, and the batch phase contains zero assistant actions; all scope
  rules pattern-keyed with reasons; QUALITY-PLAN log updated with the verdict.

## 10. Risks

- **Vision instability may be fundamental, not measurement-fragile** — protocol v2 can honestly
  stay RED. Then A/B decides: P2 showed the heuristic arm LOSES on fidelity (16/18 pages
  failed 99% on acquia), so `heuristic_arm` may trade a green model gate for a red ground-truth
  gate. The honest end may be a documented boundary, again.
- **License:** discoverasr = 4th site (acquia, supercarv2, contentfulv2 deployed); EE license
  reliably holds ~1 active. `docker compose restart jahia` clears transient violations;
  a hard block → Julian decision to unpublish/delete a reference site (destructive, escalated).
- **Content-load at 20 pages:** MCP connection resets under load are retried (rule 25), but
  this is the engine's first content epic ever — M3 is the mitigation.
- **Step-completion deadline** (600s) — settled in M2, see above.
- **Quota:** the assistant is decision-only; all heavy lifting is DeepSeek (~$0.04/run) + OVH
  vision. Expected Claude involvement in M4: monitor wakeups + roughly 5–10 decisions.

## 11. Out of scope

Cockpit UI decision panel (API-first; the web UI can come later); `autonomous` strategy
auto-pick; chunked page-group batch steps for 100+-page sites (the calibrate→batch design
holds, M4 runs at 20 pages on the existing step granularity); scope-rule actions beyond
`exclude`/`force_passthrough` (grouping/altitude overrides, renames — later); pushing commits
to the remote fork (unchanged: Julian's call); Xiaomi/MiMo provider (configured but unused).
