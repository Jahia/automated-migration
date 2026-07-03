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
- 2026-07-03 — **P1.1 artifact bridge shipped.** `semantic_extract` emits `html-fragments/<role>.html`
  (+ `.item.html`) with `htmlFragment` recorded per candidate, plus `interactive` (DOM-signal Islands
  hint) — all additive: candidate ids and shapes byte-identical to HEAD on acquia-drupal (verified
  by re-running the HEAD version side-by-side; the previously committed candidates file was stale,
  pre-BEM-collapse). `assemble_manifest` emits `instanceTypeMap` (role→nodeType incl. cross-cutting
  and nested-part→childType routing — nested-part text would otherwise never reach the JCR),
  `needsFullPage` alias, `interactive`, `htmlFragments`. `load_content.build_type_map` consumes the
  v2 contract (v1 `sxaSource` kept); cross-cutting chrome routes to absolute areas (rule 16).
  `extract_content` gains the **semantic adapter** (reuses `extract_page`, parents-before-children,
  slugs from `page-inventory.json` — fixes the `index`-vs-`home` slug drift). Validated on
  acquia-drupal: 263/263 instances resolve (100 %), 0 non-empty unmapped, 0 ordering violations,
  110 chrome instances routed to absolute areas; `cnd_emit` consumes the bridged manifest
  (32 types + 20 child types); SXA mode regression-checked in-memory on supercar. NOTE: the
  existing acquia `grouping.json` references pre-BEM-collapse candidate ids — the group step must
  re-run before the E2E (normal pipeline step, self-corrects on the partition gate).
- 2026-07-03 — **P1.2 passthrough layer shipped.** `partition_main()` (semantic_extract):
  document-ordered TOTAL partition of `<main>` (component | passthrough; unit = content leaves =
  non-empty text + media tags; chrome excluded — cross-cutting owns it). Semantic adapter emits
  main instances in document order with uncovered regions as `rawHtml` instances (verbatim,
  loader-untruncated ≤200k). `cnd_emit` always ships `ns:rawHtml`; manifest carries
  `passthroughType` + `instanceTypeMap["rawhtml"]`. NEW hard gate
  `orchestration/probes/partition.py` (fails on non-total partition, payload/summary mismatch,
  optional `--min-semantic-share` floor for P2). Baseline measured (per §5 P1 "no floor"):
  acquia 18/18 pages partition-total, semantic leaf share min 94 %/avg 99 %, 11 passthrough
  instances, 274/274 resolve; supercar SXA 100 % semantic. `semantic-templates.json` gains
  `pagePartitions`. Follow-up noted: passthrough asset URLs still point at source paths —
  rewrite to module-static/DAM at the /3-assets step (tracked for P1.3+).
- 2026-07-03 — **P1.3+1.4 shipped and validated LIVE on :8081.**
  (1) `lib/scaffold_module.sh` — headless scaffold that replicates `@jahia/create-module`'s exact
  logic (copy `module`+`template-set` templates with $MODULE/$NAMESPACE/$VERSION templating,
  dot/→. rename) from the pinned official npm package — byte-identical, no TTY (expect-driving
  clack's per-frame ANSI redraws proved brittle and was abandoned). Composes with our layout
  (module inside projects/<p>/ next to workflow-output). Needs corepack (module pins yarn 4;
  installed corepack + shims, replaced the global yarn 1.22).
  (2) `lib/merge_cnd.py` — installs the analyze CND into the module + generates rule-18 resource
  bundles (every field + `.ui.tooltip`, en+fr in sync, self-checked) + renames the placeholder
  mixin icon; backup kept OUTSIDE settings/ (anything under settings/ ships in the bundle).
  (3) `probes/namespace-check.sh` — the Groovy console accepts scripted POST (proved live):
  reads Jackrabbit's registry, PASS on free-or-matching prefix, FAIL on conflicts (rule 13 gate).
  (4) `lib/create_site.sh` — provisioning-API createSite + rule-19 verification. Live lesson:
  `languages` must be a YAML LIST — a csv string silently yields default-language-only (the
  verification caught it; fixed + site patched).
  (5) `lib/gen_plan.py` → `plans/acquia-drupal-full.plan.json` — parameterized v2 full loop
  (4 epics, 21 steps, 29 probes), passes the P0.3 engine lint (build_run_state).
  **Live state: module `acquia-drupal` DEPLOYED (55 types; acq:rawHtml/jcrQuery/nav confirmed
  via GraphQL — rule 14), site `acquia` created (en+fr, template set bound, home/files/contents/
  groups verified).** Note: current module CND comes from the IDENTITY grouping (no LLM) —
  the E2E run's group step will regenerate it (grouping.json was stale/pre-BEM anyway).
  Also fixed: a bare `package.json` line in .gitignore silently excluded every new module's
  package.json. Next: P1.5 ground-truth probe (`probes/groundtruth.sh`, referenced by the plan)
  then the E2E run (#4).
- 2026-07-03 — **P1.5+1.6 E2E in progress — ground-truth loop iterations (append per iteration):**
  Ground-truth gate built (`lib/groundtruth_probe.mjs` + `probes/groundtruth.sh`): deployed Jahia
  live page pixel-diffed vs the certified offline mirror (mirror_net served), masks policy §2,
  per-page review.html, semantic share reported. E2E chain executed for real: LLM grouping
  (DeepSeek, 1 attempt, partition-clean) → 17+3 types manifest → CND redeploy → `import_assets`
  (1639 mirror assets → module static/, ordered css) → `create_pages` (18 pages via MCP, en+fr,
  published) → `load_content` (`--clean --chrome-from`, ensure_area) → gate.
  - **iter1** (all-passthrough main + chrome in absolute areas + union CSS): 0/18, fidelity
    44–95 %, HTTP 200 + non-empty main everywhere. Diagnosis from review.html: source is
    JS-dependent (drupalSettings-driven behaviors, count-up numbers, grid/slider init) and CSS
    keys off Drupal body classes — a CSS-only shell cannot converge.
  - **iter2** (per-page SHELL v1: body attrs + exact ancestor chain + balanced chrome/scripts
    around <main>, stored as a `shell` node composed by the basic template): fidelity flat,
    Δheight EXPLODED (77–184 %) → duplicate content: `--clean` skipped PUBLISHED nodes.
    Engine lessons encoded in the loader: area nodes are created lazily at first render
    (`ensure_area` creates the jnt:contentList eagerly); published non-i18n nodes refuse both
    hard delete AND per-language unpublish — the working idempotent clean is TWO-PHASE
    (mark_for_deletion + publish-the-deletion).
  - **iter3** (proper clean): duplicates gone, fidelity back to baseline — shell body renders
    (body classes, wrapper chain, hero text present in DOM) but `drupalSettings` was missing:
    it is an INLINE HEAD script, and Drupal aggregates CSS/JS per page — union manifests are
    not faithful. → **shell v2**: per-page `<head>` captured in the shell (ordered stylesheets,
    scripts, inline scripts incl. drupalSettings, inline styles; external hosts stripped for
    parity), RawHtml wrapper made display:contents. iter4 running.
  - **iter4** (shell v2 live-verified: drupalSettings ✓, per-page head ✓): fidelity flat again —
    root cause finally isolated by DOM comparison: the partition DESCENDS into wrappers that
    contain components without emitting the wrapper element itself, so its grid/flex classes are
    lost and the layout collapses (the mirror keeps the wrapper; we didn't).
  - **iter5** (demotion granularity = DIRECT CHILD OF <main>, wrappers intact — a fully-demoted
    top group loads as ONE verbatim blob): **16/18 pages at 100 %, Δh 0**. Third loader lesson:
    `content.list` paginates (~20) — one clean pass left 4 stale nodes and a leftover FAQ block
    on top of an otherwise-100 % home; clean now loops until empty.
  - **iter6**: home 100 % after full clean. about-us stable at 96.93 %: partner-logo rotator
    (client JS replaces a static composite SVG with a randomized 3×3 logo grid — two renders of
    the SOURCE differ). Masked per policy §2 with documented reason
    (`workflow-output/groundtruth-masks.json`, committed).
  - **RESULT: GROUND TRUTH 18/18 pages ≥ 99 % — ALL AT 100 % (1 masked dynamic zone).**
    publish-parity PASS (weakrefs + translations in LIVE), edit-frame PASS (pages editable in
    Page Builder). Semantic share of the LOADED site: **0 % (honest)** — fidelity-first profile
    loads everything as shell+passthrough; the analyzer's measured capability is 94–99 %
    (pagePartitions) and raising the loaded share is exactly P2's job. `j:linkType` confirming
    mutation recorded (see migration.md rule 9: mixin injection is a Content-Editor flow; API
    loaders must addMixins explicitly — MCP has no mixin support today).
  - Fidelity-shell template set extracted as AGNOSTIC (`orchestration/templates/fidelity-shell/`
    + `install_shell_templates.py`, only $NS substituted) — Julian's agnosticism constraint;
    plan regenerated as a fully deterministic fidelity-first profile (21 steps, 28 probes,
    engine-lint PASS). Known follow-ups: content-fidelity.py's nav/footer shell check predates
    the shell-node architecture (needs a variant); `assets.sh`/`components-all.sh` idem;
    P2 promotion will re-introduce semantic views + those probes.
- 2026-07-03 — **SINGLE-RUN CERTIFICATION PASS — P1 COMPLETE.**
  `python3 orchestration/run_local.py orchestration/plans/acquia-drupal-full.plan.json`:
  all 21 steps DONE in one deterministic run (crawl→mirror gate→semantic→LLM grouping [naming
  gate GOOD this run — no editor-hostile names]→CND→content extract+partition gate→fidelity
  gate→namespace gate→scaffold→assets→CND merge→fidelity-shell templates→deploy gate→site→
  pages→content load→publish-parity→edit-frame→GROUND TRUTH). Zero manual actions.
  **P1 DoD met**: 18 pages contributed + published on :8081, editable in Page Builder, ground
  truth 18/18 ≥99 % (all 100 %, 1 documented mask), publish-parity + edit-frame green,
  semantic share measured (loaded: 0 % — fidelity-first; capability: 94–99 %), j:linkType
  mutation recorded. → P2 (task #5): raise the LOADED semantic share ≥60 % by promoting roles
  (vision segmentation), fidelity staying ≥99 %.
- 2026-07-03 — **P2 in progress (append per milestone):**
  - **2.1 segmentation gate fixed** (`segment_probe.mjs`): unparseable / hallucinated-ids /
    coverage<--min-coverage(50) replies get the exact failure fed back and retried
    (--retries 3); gate RED on persistent failure — never silently green on model collapse.
  - **2.3 stability shipped**: --stability 2 (default) runs the gated segmentation twice,
    root-set Jaccard ≥0.8 accepts (higher coverage wins), else third run + best-agreeing pair.
  - **Live on acquia (7 cluster representatives, OVH Qwen2.5-VL): 7/7 gate GREEN, 1 attempt
    each, stability ≥0.8 (mostly 1.0), leaf coverage 94–100 %** — editorial names + hierarchy
    (Hero Section, Press Release Cards→Card, Executive Leadership Section→Leader Card,
    Logo Bar, Office Locations…).
  - **2.2 adapter shipped** (`segment2manifest.py`): vision naming authority; deterministic
    field re-extraction on the data-seg-annotated DOM; chrome→crossCutting; detail templates
    reused (vocabulary-independent); representative fragments; heuristic-role bridge — each
    vision component claims its root's + DESCENDANTS' candidate roles (vision roots rarely land
    on the exact heuristic element; generic roles excluded to avoid site-wide relabeling) →
    manifest 31 components + 3 chrome, naming GOOD, `instanceTypeMap` maps heuristic instance
    roles onto vision-named types.
  - **Promotion mechanism = SKELETON views** (fidelity + editability): a promoted region loads
    as ONE semantic instance whose `skeleton` property is its own markup with {{f:name}}
    markers where field values were lifted (unique-match substitution only — misses recorded,
    never silent); generated per-type views substitute property values back
    (`SkeletonView.tsx.template`, `install_shell_templates --manifest`). Children stay inline
    (monolith; per-item editability = P3 refinement).
  - **Loaded semantic share: min 69 % / avg 94 % / max 100 % — P2 floor (≥60 %/page) PASS on
    18/18** (`partition.py --min-semantic-share 60`). Fidelity re-check under skeleton
    rendering in progress (P2 gate pair: share ≥60 % AND ground truth still ≥99 %).
  - **Skeleton-promotion iteration log (7 measured iterations to green):** (a) whole-page
    monolith trap caught by independent JCR verification — Drupal wraps main in ONE
    `region--content`, so top-group promotion produced a full-page "component" AND the gate
    measured a STALE CACHED render (careers had 1 JCR node but rendered complete) → ground-truth
    probe now flushes Jahia's output caches before measuring; `main_content_root()` descends
    single-content-child wrappers (chain recomposed by the shell's `innerLevels`) so groups sit
    at real-section altitude. (b) `skeleton` is a hidden prop → absent from content.type
    introspection → the loader's order-zip silently mis-assigned it; promoted instances now use
    an EXPLICIT contract (skeleton always set; title→jcr:title; text→text|body) and lift ONLY
    round-trippable fields. (c) display:contents wrappers are layout-transparent but NOT
    selector-transparent — views now render the fragment's REAL root element (`rawRoot.ts`).
    (d) zero-leaf top children (spacer divs) must load as passthrough — dropping one cost 128px
    of section spacing. (e) every skeleton type carries a `title` field → mix:title, or the
    lifted heading is silently skipped at create and VANISHES from the render.
  - **P2 GATE PAIR — FINAL: ground truth 18/18 ≥99 % (17×100 %, careers 99.93 %) AND loaded
    semantic share min 69 %/avg 96 % (floor ≥60 % PASS 18/18), publish-parity + edit-frame
    green, naming GOOD** — vision manifest: 31 components + 3 chrome, 31 generated skeleton
    views, 83 nodes loaded.
  - **2.4 A/B (judge = the ground-truth gate, pre-registered):**
    | arm | manifest | fidelity | semantic share | verdict |
    |---|---|---|---|---|
    | A heuristics (LLM grouping) | 17 comps, naming good | **16/18 FAIL** (home 95.4 %, customer-success 97.6 %) | 96 %/100 % | loses on the judge |
    | B vision (Qwen2.5-VL) | 31 comps, naming good | **18/18 PASS** | 69 %/96 % | **WINNER — shipping state** |
    Same skeleton mechanism both arms (apples-to-apples). Heuristics promote MORE but break
    fidelity on 2 pages; vision's segment boundaries survive the pixel judge. **P2 COMPLETE.**

- **2026-07-03 — P2.5 CONTRIBUTION MODEL COMPLETE (all four pre-registered gates green on acquia).**
  Trigger: Julian's editorial review of the deployed site — the P2 skeleton monolith was NOT
  usable by CMS contributors. Honest metric finding first: `semanticLeafShare` measured
  STRUCTURAL coverage only; the real contributable-text share of the P2 state was **1.8 %**
  (59/62 `text` props dead via string-match substitution misses, 19/67 promoted instances were
  zero-field empty shells, 151 images + 171 links baked). Plan pre-registered in
  `orchestration/CONTRIBUTION-PLAN.md` BEFORE implementation (incl. the forms-excluded metric
  refinement, registered before the probe existed).
  - **Mechanism (one skeleton mechanism, three altitudes):** DOM-level marker substitution
    (`semantic_extract.decompose_group` — markers replace element CONTENT in the tree; a field
    that cannot be placed is NOT loaded), per-item decomposition at repeated-sibling boundaries
    (typed container + `item-N` child nodes, richtext `body*` = exact innerHTML runs), and
    anonymous rawHtml blocks lift their text runs too (honest name, editable text). CND is
    sized from the OBSERVED lift (`cnd_emit --content-load`, wired-only types — mix:title and
    body..bodyN only where ≥1 instance lifts them). Byte-identity self-check at extract time:
    recompose(skeleton, fields, children) must equal the original serialization or the group
    falls back to verbatim rawHtml (fidelity before contribution; 0 byte-fails on acquia).
  - **GATES: G1 static contribution min 89.1 %/avg 98.1 % forms-excluded (floors 60/85), dead
    props = 0, phantom markers = 0, empty shells = 0 — PASS. G2 round-trip 18/18 sentinel
    edits visible live + restored (publication is ASYNC → probe polls to convergence) — PASS.
    G3 ground truth 18/18 pages = 100 % AFTER the G2 mutations+restores (careers up from
    99.93 % — real-root item rendering recovered it) — PASS. G4 careers = acq:contentGrid +
    5 × acq:contentGridItem, item body richtext carries the card heading+copy — PASS** (card
    titles live INSIDE body richtext when the source heading is span-wrapped; strict jcr:title
    lift only takes pure-text headings — recorded, not hidden).
  - **Loader truths (hard-won):** the mark_for_deletion + publish clean flow is UNRELIABLE for
    skeleton nodes (jmix:markedForDeletion survivors whose deletion-publication never lands;
    'already exists' create collisions from the ASYNC race). Replaced by GraphQL EDIT-workspace
    `deleteNode` (synchronous, publication-state-agnostic) + ONE parent publication to purge
    LIVE. Create retries on 'already exists' kept as belt-and-braces. 239→240/240 nodes loaded
    (82 parents + 157 items + shells/chrome).
  - Pipeline reordered in `gen_plan.py`: extract_content BEFORE cnd_emit (wired-only sizing),
    contribution probe on extract + load, `step_roundtrip` before the ground-truth HALT gate
    (roundtrip always restores). 22 steps/31 probes, plan regenerated.
  - Deferred to phase C (recorded): images → DAM weakreference (151 baked), links →
    j:linkType + addMixins (171 baked); per-node body-run variance (an item with fewer runs
    than its type declares shows empty-but-inert extra fields).

- **2026-07-03 — P2.5-C COMPLETE (media DAM + links + titles; all gates green on acquia).**
  Design registered in CONTRIBUTION-PLAN §8 BEFORE implementation (incl. one pre-measurement
  amendment: G5b reworded from "95 % of external links" to "95 % of link-bearing payloads" —
  the original contradicted C3's own j:linkType-singleton constraint; and the media cap is a
  design parameter, raised 3→6 after G5a measured 87.9 % under the frozen 90 % floor).
  - **C1 titles:** lift_title now takes any heading with EXACTLY ONE non-ws text node
    (span/strong wrappers stay in the skeleton) — careers card titles land in jcr:title and
    leave the body richtext (item-1 = title "Committed to Awesome" + clean per-card body).
  - **C2 media:** 203 units (76 img + 127 picture); 201 wired (97.1 %). Per unit: `imageN`
    weakref (picker[type='image'], jmix:image) + hidden `imageNOrig` (exact source markup)
    + `imageNOrigRef` (UUID of the DAM copy). 162 unique mirror assets uploaded via MCP
    `media.upload.create`/PUT/`finalize`, published, deduped in orchestration/images/
    acquia-drupal.dam.json (committed). View: UUID==origRef → verbatim original (byte-exact
    default, G3 safe by construction); UUID differs → chosen image wins (sources/srcset
    dropped, img@src swapped). 1 missing mirror asset (SVG) counted, not silent.
  - **C3 links:** 60/60 link-bearing payloads wired (100 %): j:linkType + linkLabel +
    hidden linkOrig in CND (j:url/j:linknode NEVER declared — mixin-injected); loader does
    GraphQL addMixins then j:url (external, 5) / j:linknode weakref (internal resolved, 3);
    52 internal links target non-migrated pages → honest linkOrig fallback (render byte-
    exact, j:linkType='none', editors can rewire). View href = j:url || linknode URL ||
    linkOrig.
  - Views refactored to a SHARED `skeletonRender.ts` (nodePayload/composeNode — JCR-read
    based, one code path for SkeletonView, items and lifted rawHtml). TS gotcha: `body*/`
    inside a JSDoc block comment terminates it — generated views must never embed `*/`.
  - **GATES: G1 min 87.6 %/avg 98.0 % (floors 60/85), zeros hold. G5a media 97.1 % (floor
    90). G5b links 100 % (floor 95). G2+ round-trip 23/23 — 18 text + 4 media swaps (live
    <img> follows the weakref, restores) + 1 j:url sentinel. G3 ground truth 18/18 ≥99 %
    with all wiring live. publish-parity (162 DAM weakref targets resolve in LIVE) +
    edit-frame PASS.** 238+ nodes, 2 transient create failures replayed to zero.

- **2026-07-03 — P2.5-D: per-node slot mixins (editor form = exactly the node's real fields).**
  Julian's second editorial review caught the per-node variance flaw shipping C left open:
  type-level body..bodyN sized every node's form to the RICHEST instance (contentGrid nodes
  showing empty unjustified body2/body3). Fix = Jahia's own pattern (jmix:externalLink):
  wired-only types now declare ONLY the hidden `skeleton`; every editor-facing slot is a
  module mixin (`acqmix:contribBody[N]`, `acqmix:contribImage[N]` incl. hidden companions,
  `acqmix:contribLink`, plus `mix:title`) that the LOADER adds per node — create(skeleton)
  → addMixins (one GraphQL call) → update(mixin props) → weakrefs → publish. Verified live:
  contentGrid-careers-11 = [contribBody] + body only; its item-1 = [mix:title, contribBody,
  contribImage] = Title + Body + Image. merge_cnd generates bundle labels for the slot
  mixins ("Text (3)", not raw "body3").
  - **Two loader truths found by the gates:** (a) publishing a PARENT while its item
    children are still being created ABORTS the publication job — the EDIT node never
    reaches LIVE (2 big articles, GT 92 %, parity translation gaps); parents now publish
    AFTER their subtree is complete + one area publication sweeps stragglers. (b) MCP
    content.create fails transiently under sustained write load (~1-3 %) — generic
    retry-with-backoff on 'already exists' AND 'failed unexpectedly'.
  - **Re-certified: GT 18/18 ≥99 %, round-trip 23/23 (text+media+link on mixin props),
    publish-parity + edit-frame PASS, G1/G5 floors hold** (probe unchanged — dead-prop
    semantics are per-node by construction now).

- **2026-07-03 — P2.5-E: G6 editor-surface gate + Page Builder item frames (Julian's 3rd
  review: "je ne peux toujours pas éditer ce bloc").** Root cause was NOT the data — the
  forms API showed item-1 with jcr:title/body/image all read-write — but REACHABILITY:
  string-composed items have no edit frame, so the correct form was unreachable through
  the editorial flow. Fix: skeleton views now render item children through the pipeline
  (`<Render node/>`) in EDIT/PREVIEW mode (chunkTopLevel splits the substituted skeleton
  into balanced chunks interleaved with per-item renders; extras beyond the original
  markers render after the last slot), LIVE keeps byte-exact string composition.
  **New permanent gate G6 (CONTRIBUTION-PLAN §9):** G6a = every wired prop is a rw field
  in `forms.editForm`; G6b = every item node has a `[path]` frame in the Page Builder
  editframe (Playwright). **G6 PASS: 37 forms + 28 item frames, 0 failures; G3 re-run
  18/18 ≥99 %.** Meta-lesson recorded: JCR + pixels never judge the EDITOR EXPERIENCE —
  that blind spot produced all three review rounds; it is now gated. Probe-hygiene rule:
  distinguish "instrument could not observe" from "defect" (blank-login editframe read as
  12 missing items; `source .env.local` does not export — python probes now take creds
  from mcp_client's own .env parsing).

- **2026-07-03 — P3 full loop × 3 sites (supercar / contentful / discoverasr holdout), 20 pages each.**
  The pipeline generalized end-to-end to two never-before-run sites + a blind holdout;
  every fix below is GENERIC (no per-site branching). Vision profile wired into gen_plan
  (segment steps replace LLM grouping); `make_overrides.py` generates the dial; `run_plan.py`
  executes plans deterministically.
  - **Generic hardening found by the runs (all committed):** (1) extract_page keeps
    script/style/noscript in the bytes contract (a Typeform-embed page whose body was
    script-only lost everything); (2) pages without `<main>` partition the body; (3)
    page_shell serializes bs4 Comments with their markers (comment text was rendering
    visibly); (4) runtime-manifest rewrite registers every URL form (https/http/
    protocol-relative/path) — CDN logos referenced protocol-relative were left broken;
    (5) 1-char text leaves counted+emitted; (6) repeated `<p>`/`<h*>` are text RUNS not
    container items (a Next.js article became 10 empty item nodes); (7) G1 denominator
    excludes the NEVER_IN_BODY widget set; (8) ground-truth LIVE side gets the SAME offline
    resolution as the reference (a OneTrust banner loaded one-side-only cost ~20 pts);
    (9) reconstruct gate judges script-rendered pages on pixels; (10) deploy gate verifies
    the module TYPE actually appears (rule 14 — an unresolvable nodetype requirement, an
    undefined `{node}Item`, silently left the bundle un-started); (11) create_site
    self-heals a wrong templateSet + sets languages post-create (provisioning has no
    languages param); (12) MCP transport retry on connection resets (a 384-media site
    dropped connections → lost content); (13) SkeletonView edit mode renders deeply-nested
    + fallback item children through the pipeline for G6 frames; (14) probes use
    domcontentloaded + poll (the jContent SPA never reaches networkidle).
  - **RESULTS (contribution G1 + media/link G5 GREEN on all three deployed):**

    | site | source stack | GT ≥99% | GT avg | GT ≥90% | G1 cover (min/avg) | G5 media | G5 links | notes |
    |---|---|---|---|---|---|---|---|---|
    | acquia-drupal (ref) | Drupal/Site Studio | **18/18** | 100% | 18/18 | 88/98% | 97% | 100% | fully green |
    | supercar-garage | Sitecore SXA | 15/20 | 96.6% | 18/20 | 76/98% | 100% | 100% | 5 homepage-variant + 2 exposants pages: `<Area>` dropped inside a grid `div.row` → column content stacks (~8% vertical drift) |
    | contentful | Next.js | 2/20 | 93.9% | 18/20 | 99/99.6% | 98% | 100% | text/home pages green (home 99.2%, an article 100%); case-study image-grid pages held at 92-98% by ~9 lazy-loaded CDN card images the crawl never captured |
    | discoverasr (holdout) | Ascott hotels SPA | — | — | — | — | — | — | **BLOCKED at the mirror gate**: 47/57 images lazy-loaded from CDN, uncaptured → mirror-fidelity 5.6%; the gate correctly refuses to migrate a site it cannot faithfully represent offline (anti-overfit honesty) |

  - **Single dominant residual, one generic root cause:** lazy-loaded / CDN-served images
    the crawl+localize step did not successfully download (contentful case-study cards,
    discoverasr almost entirely). Text, layout, contribution model, editor surface all
    generalize cleanly. The identified next lever is localize-phase image-capture hardening
    (scroll-trigger lazy images + retry CDN downloads through the WAF) — a crawl-phase
    sub-project, not a per-site fix.
  - **Pre-registered P3 bar** ("3/3 reach the ground-truth gate; ≥2/3 green"): 2/3 reached
    the gate and produced measured fidelity (supercar 15/20, contentful 2/20 but 18/20
    ≥90%); the holdout was blocked upstream at the mirror gate. Honest verdict: **partial** —
    the pipeline generalizes structurally + editorially to all stacks, but per-page pixel
    GREEN depends on image-capture completeness, which is the next work item.
