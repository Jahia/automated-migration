# QUALITY-PLAN — end-to-end quality & reliability plan (v2 pipeline)

> **Status: ACTIVE — governing document.** Written 2026-07-03 after a repo-wide recon + adversarial
> critique of the draft plan. Thresholds below are **pre-registered**: they were fixed *before* the
> work started and may only be changed by editing this file with a dated justification — never
> retroactively to make a run pass.

---

## 1. Governing principle

The v1 thesis said **deterministic**. The pivot to LLM-vision segmentation makes that word wrong.
The replacement is **verifiable**:

- LLM steps (grouping, vision segmentation) produce free output — no attempt to make them byte-stable.
- Every LLM output passes through a **deterministic gate** (partition, coverage, naming, stability)
  before anything downstream consumes it. A bad output fails and retries; it never silently flows.
- Everything that *can* be deterministic (extraction, assembly, CND emission, probes, mirrors) stays
  deterministic.

Second principle: **ground truth first**. Every fidelity number produced so far is self-referential
(the analyzer scoring its own reconstruction against its own mirror). No further upstream gate
polishing until one site has crossed the full pipeline into a deployed Jahia site, measured by a
**ground-truth gate** (Jahia live render vs source mirror).

## 2. The two-metric invariant (non-negotiable)

Since the "RIEN supprimer / pixel-perfect" decision, quality is TWO numbers, never one:

| Metric | What it measures | Target | Negotiable? |
|---|---|---|---|
| **Render fidelity** | Pixel diff: Jahia live page vs source local-mirror render (after declared masking) | **≥ 99 % per page, every page** | **NO — hard invariant from the first E2E run (P1)** |
| **Semantic share** | % of page content living in real editorial components (vs raw-HTML passthrough) | Quality dial — rises by phase (see §5) | Yes — floors per phase, pre-registered |

The passthrough layer is what makes the first row possible from day one: every DOM region is either
a semantic component or a raw-HTML passthrough node — **nothing is ever dropped**. A migration that
is 100 % faithful but 95 % passthrough passes metric 1 and fails metric 2: pixel-perfect but
editorially useless. Both gates must be green.

**Honesty note:** "≥ 99 % measured" — not "100 % by construction". A re-rendered HTML fragment
depends on ancestor CSS cascade, fonts, and dynamic content. Residual diffs must be *visible and
explained* in the gate report, never silently absorbed.

**Masking policy:** only regions listed in `workflow-output/groundtruth-masks.json` (per site,
committed, each entry carries a `reason`) may be excluded from the pixel diff — genuinely dynamic
zones only (carousels, dates, cookie banners, live feeds). Masks are reviewed at the gate. No mask,
no exclusion.

## 3. Environment truth (verified live 2026-07-03)

- The running Jahia is **`http://localhost:8081`** (`docker/docker-compose.yml` maps `8081:8080`);
  super-user credentials live in `.env.local` (see `.env.example` — NOT the CLAUDE.md defaults).
  **Port 8080 is an unrelated container**
  (email-sorter) that answers `{"detail":"Not Found"}` — easy to misread as a Jahia auth problem.
- The CSRF `Origin` header is **port-sensitive**: `Origin: http://localhost:8080` against :8081 is a
  hard, empty-body 403. The Origin must match `$JAHIA_URL`.
- Instance state: only `systemsite` exists; **no migration site, no migration module deployed**.
  A Jahia **MCP server is provisioned** (`jahia-mcp-community-server` + `mcp-servlet`) — the
  sanctioned content-write path (`orchestration/lib/load_content.py` → `mcp_client.py`).
- Consequence: all URLs/credentials come from **environment** (`.env.local` at repo root, gitignored;
  committed `.env.example` documents the variables). Hardcoded `localhost:8080` / `root:root` in
  docs, probes, or plans is a P0 defect.

## 4. Key recon findings the plan builds on

1. **The downstream half already exists (v1).** `orchestration/plans/supercar-garage.plan.json` & co
   run scaffold→assets→CND→components→templates→deploy→content→fidelity headless under the
   orchestrator, with ~15 committed probes (`deploy.sh`, `content.sh`, `publish-parity.sh`,
   `edit-frame.sh`, `fidelity-live.sh`, …) and human HALT gates. The real work is the
   **v2→downstream artifact bridge**, not inventing the downstream.
2. **Bridge gaps (P1 scope):** v2 manifest lacks `htmlFragment` (semantic_extract keeps samples, not
   outerHTML), `interactive`, `needsFullPage` (v2 says `needsMainResource`), and the instance→type
   map `load_content.build_type_map()` needs. Nothing consumes `definitions.cnd`/`views.json` into a
   module. Scaffold needs a TTY. `/6-content` hard-fails without `content-data.json` (v2 doesn't
   produce it — drive `load_content.py` directly instead).
3. **Engine integrity gaps (P0 scope):** gate "reject" is a functional no-op (a later resume
   *approves* a human-rejected gate); steps without `PROBE:` lines auto-pass even on unparseable
   agent output; no `deploy`/`groundtruth` gate types; `PROBE_TIMEOUT_S` fixed at 600 s (a cold
   `yarn install && yarn build` can exceed it); no secrets mechanism (inline creds would persist
   into sqlite `state_json`, `prompt_text`, and the audit log).
4. **Segmentation prototype gate is weaker than believed:** an unparseable vision reply →
   0 components → everything passthrough → `gatePass: true` (it only checks hallucinated ids).
   It probes 1 page (`slice(0,1)`), has no caching, and is wired into no plan.
5. **Already settled — do not redo:** the `j:linkType`/`j:url`/`j:linknode` convention was resolved
   empirically against the three deployed reference modules (ANALYZE-PIPELINE.md §"CND link
   convention"; `cnd_emit.py` encodes it). Remaining: fix `.claude/rules/migration.md` rule 9 +
   one confirming mutation after the first v2 deploy.

## 5. Phases

### P0 — Environment truth + engine integrity (2–3 days)

| # | Work | Gate (pass/fail) |
|---|---|---|
| 0.1 | Parameterize `JAHIA_URL`/`JAHIA_USER`/`JAHIA_PASS`/Origin everywhere (probes, lib, docs). `.env.example` committed, `.env.local` gitignored. Fix CLAUDE.md + `.claude/rules/jahia.md`. | `orchestration/probes/connect.sh` green from env alone; `git grep` finds no live hardcoded `localhost:8080` outside docs-as-default/examples |
| 0.2 | Secrets: verifier injects env from `.env.local` into probe subprocesses; plans reference `$VARS`, never literal creds. Then **rotate exposed OVH/DeepSeek keys (Julian action)**. | Regression: probe sees `$JAHIA_URL`; no secret string in `orchestrator.db` state_json for a test run; old keys refused |
| 0.3 | Gate integrity: persistent **rejected** state (reject ≠ no-op; plain resume never approves a halted gate — only the typed approve endpoint does); plan lint (deploy/content steps must carry ≥1 PROBE); `deploy` + `groundtruth` gate types; `PROBE[<seconds>]:` timeout override + env default. Update CONTROL-LOOP.md. | pytest regression suite: "reject-then-resume ≠ done", "resume leaves halted halted", lint rejects a PROBE-less deploy step |
| 0.4 | Doc honesty: thesis wording "deterministic" → "verifiable" (ANALYZE-PIPELINE.md); fix migration.md rule 9. | Reviewed diff; no new claims without evidence |

### P1 — Ground truth: ONE site end-to-end, orchestrator-driven from day 1 (1–2 weeks)

Site: **acquia-drupal** (pure v2 provenance, no v1 module → no Jackrabbit namespace trap, the one
committed v2 plan already targets it). Supercar second — with a **fresh namespace** (`usg` v1 exists).
Contentful is the exit criterion, not the test bench.

| # | Work |
|---|---|
| 1.1 | **Artifact bridge**: semantic_extract persists representative outerHTML → emit `workflow-output/html-fragments/`; manifest gains `needsFullPage` (alias), `interactive`, instance→type map; synthesize the v2 `content-load.json` from the mirror (extract_content v2 adapter) |
| 1.2 | **Minimal passthrough layer** (pulled forward from old P2 — required for the ≥99 % invariant): manifest `passthrough[]` → `ns:rawHtml` CND type (seed: `usg:plainHtml`) → loader creates passthrough nodes. Hard partition gate: every source region covered exactly once |
| 1.3 | Headless scaffold (committed expect-wrapper or template checkout); CND merge into module `settings/definitions.cnd` (+ `types.ts`, resource bundles with `ui.tooltip`); **scripted** namespace-conflict check (Groovy console is browser-only today); site creation via provisioning API |
| 1.4 | **Parameterized v2 full-loop plan** (graft the v2 analyze epic onto the v1 template; `acquia-analyze.plan.json` is single-site-hardcoded) |
| 1.5 | **Ground-truth gate**: compose `fidelity-live.sh` (dual headless render) + reference = local-mirror served by `mirror_net.mjs` + pixel diff à la `reconstruct_probe` → `groundtruth/review.html` |
| 1.6 | Run acquia-drupal end-to-end through the orchestrator; iterate until green |

**P1 pre-registered gates:** render fidelity **≥ 99 %/page** (masking policy §2); 100 % of migrated
pages return HTTP 200 in live with non-empty main content; `publish-parity.sh` and `edit-frame.sh`
green; **semantic share measured and reported, no floor** (this is the baseline); zero manual
actions outside approving the human HALT gates. One confirming `j:linkType` mutation recorded.

**DoD:** ≥ 8 pages of acquia-drupal contributed + published on :8081, editable in jContent, all
gates green, from a single orchestrator run.

### P2 — Segmentation raises the semantic share (2 weeks)

The vision segmentation no longer "achieves fidelity" (P1's passthrough already guarantees it);
its job is to **move content from passthrough into semantic components**.

| # | Work |
|---|---|
| 2.1 | Fix the segmentation gate: fail/retry when semantic leaf-coverage < 50 % or reply unparseable (today: GREEN on total model failure) |
| 2.2 | Adapter segmentation→manifest on ONE site: stable cross-page ids, per-segment field re-extraction (vision output has no dataShape), multi-page aggregation (today `slice(0,1)`), naming authority = vision names / naming-quality gate verifies, chrome→crossCutting. Heuristics demoted to prior/fallback behind a flag |
| 2.3 | Stability: N=2 agreement check per cluster (component-set Jaccard ≥ 0.8 else third run + majority); caching deferred until multi-cluster probing exists |
| 2.4 | A/B LLM-vs-heuristics judged by the **P1 ground-truth gate**, not the self-referential pixelSim |

**P2 pre-registered gates:** semantic share **≥ 60 %/page** on the wired site with fidelity still
≥ 99 %; segmentation gate red on <50 % coverage; stability check green.
Deferred (explicitly): tall-page tiling, 2-representatives-per-cluster, cluster-hash cache.

### P3 — Full loop × 3 sites + cockpit (1 week)

Rerun supercar/liferay/contentful through the parameterized full-loop plan.
**Pre-registered success:** 3/3 reach the ground-truth gate; ≥ 2/3 green at thresholds.
Cockpit: ground-truth panel (Jahia vs source side-by-side) + semantic/passthrough KPI; un-hardcode
the rerun endpoints in `runs.py`. Liferay×vision = separate experiment, gates nothing.

### P4 — Anti-overfit proof: holdout site (days + the run)

A 6th **never-seen** site, chosen before P2 completes. **Thresholds frozen NOW:** render fidelity
≥ 99 %/page, semantic share ≥ 50 %/page, zero manual interventions outside human gates. Post-hoc
grading is the exact failure mode this phase exists to prevent. Heuristic demotion (BG_CLASS_RE,
heading keywords) only once vision segmentation covers those cases on the 5 reference sites.
Crawler JS-render only if the holdout demands it.

## 6. Cut from the draft (with reasons)

- Standalone `j:linkType` experiment — already answered (see §4.5).
- Full thesis rewrite — targeted wording pass suffices (honest-scope blockquote already exists).
- Contentful inside P1's core — multiplies bridge failures before the path is green.
- Immediate segmentation caching — one OVH call/run today; cache waits for multi-cluster.
- "Revisit liferay with vision" inside industrialization — research detour, gates nothing.

## 7. Execution log (append-only)

- 2026-07-03 — Plan written. P0 started.
- 2026-07-03 — P0 implemented (env truth + secrets injection, engine gate integrity + 12 tests,
  doc honesty) and verified (mechanical: green; adversarial: 3 restart-path defects found).
  Session stopped on quota BEFORE the fixes and the commit — see `QUALITY-PLAN-WIP.md` for the
  exact resume state.
- 2026-07-03 — The 3 restart-path defects fixed + committed. (1) `normalize_for_resume` resets
  `running` stories/epics to `pending` (approve-after-engine-restart no longer insta-fails the
  run); (2) `jump_to_step` spawns a fresh `_run_loop` when none is active (no zombie run; jump is
  a working redo path for `rejected` after restart); (3) `compact_status` surfaces a rejected step
  as the blocking gate with `next_actions=[rollback, jump, restart]` (+ new `gate.status` field).
  Minor: `rejected` added to frontend `StepStatus` and `schema.py` states (incl. missing `halted`).
  pytest 16/16 (4 new regression tests). **P0 complete.**
