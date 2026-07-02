# Deterministic analyze pipeline (v2) — component & template identification

Canonical reference for the reworked **analyze phase**: turn a source website into a
Jahia component + template model that is **deterministic, agnostic, right-grained,
and fidelity-verified before templatization**. Supersedes the block-explosion of
`extract-blocks.py` (256 raw blocks / 10 pages) and the orphaned `hybrid-identify.py`
(clustered by structure, found 0 cross-cutting).

> **North star:** reconstruct sample pages from ONLY the extracted elements and prove
> they render identically to the source — *before* adding Jahia's complexity. If the
> reconstruction matches, extraction is complete; the diff localises exactly what the
> template + asset-import must supply.

---

## 1. Where the boundary sits (the thesis)

Not "heuristics *or* LLM" — a layered pipeline where the LLM only makes the one
irreducible semantic judgment, bounded and gate-verified:

| Stage | Who | Guarantee |
|---|---|---|
| Crawl | deterministic | cache-first |
| Localize (self-contained local mirror) | deterministic | **offline-render gate** (0 external static assets) |
| Candidate extraction (altitude + data-shape + frequency + cross-cutting) | deterministic | **byte-stable across runs** |
| Grouping (which candidates = one Jahia type) | **LLM, bounded** (partition of candidate ids only, temp 0, self-correcting) | gate-verified |
| Assemble (names, fields, child types, layout props) | deterministic | **naming variance = 0** |
| Gates (partition, dup-shape sanitizer, stability, fidelity) | deterministic | non-zero exit blocks |

Measured: deterministic layer 3× byte-identical; grouping stability 95–99% (naming-
invariant); cross-cutting 100%; every DeepSeek run passed the partition gate on the
first attempt (0 hallucination / 0 omission).

---

## 2. The tools (`orchestration/lib/`)

| Tool | Purpose | Usage |
|---|---|---|
| `crawl-site.py` | cached, rate-limited crawl + assets → `page-inventory.json`. (urllib — **no JS render**; fine for server-rendered SXA/Drupal, a gap for JS-hydrated sites.) | `python3 crawl-site.py <proj> <url> --max-pages N --depth D` |
| `localize_site.py` | **build a TRULY-LOCAL mirror** from the crawl cache: discover every asset (HTML refs **+ recursion into CSS** `@import`/`url()`/`@font-face`), download the missing (cache-first, WAF-aware), rewrite ALL refs (HTML+CSS) to hash-named local paths → `workflow-output/local-mirror/<slug>.html` + `assets/` + `mirror.json` (residue + localizable %). Deterministic. | `python3 localize_site.py <proj> [--max-asset-size MB]` |
| `mirror_probe.mjs` | **the local-mirror gate.** Serves the mirror from an ephemeral 127.0.0.1 server and renders each page with **every other origin blocked**. GATE = zero blocked *static-asset* requests (css/font/image/script/media) that aren't a known tracker/residue (runtime beacons/xhr are ignorable); asserts stylesheets applied. Also pixel-diffs offline-vs-live → **mirror-fidelity %**. Writes `mirror/mirror-review.html`. | `node mirror_probe.mjs <proj> [maxPages] [--pages a,b] [--all] [--no-live]` |
| `semantic_extract.py` | **deterministic candidates.** SXA fast-path (`class="component"`) + agnostic recursive **altitude finder** (descend single-block wrappers → first multi-block "component row" → stop; titled sections kept whole). Data-shape signatures, cross-page frequency, **cross-cutting by ubiquity+position**, template clusters. | `python3 semantic_extract.py <proj>` → `semantic-candidates.json`, `semantic-templates.json` |
| `grouping-prompt.md` | the site-**agnostic** grouping prompt (feature-driven, no site/CMS names). Merge liberally by shape; the sanitizer splits bad merges. | consumed by `group_llm.py` |
| `group_llm.py` | **the single bounded LLM step.** Calls DeepSeek V4 Flash (temp 0) with the compact candidate set; self-corrects on the partition gate. | `python3 group_llm.py <proj> --model deepseek-v4-flash --ns <ns>` → `grouping.json` |
| `assemble_manifest.py` | **deterministic** manifest: computes nodeType/fields/child from the grouping; partition gate (no-new-types + coverage); `sanitize_groups()` splits shape-incompatible LLM grab-bags; `--consensus` fuses N runs. | `python3 assemble_manifest.py <cand> --group <grouping> --ns <ns> --out <manifest>` |
| `stability_gate.py` | count + **naming-invariant grouping stability** (role-pair co-membership) + cross-cutting + gates over N runs. | `python3 stability_gate.py <adj-dir> <cand>` |
| `cnd_emit.py` | **deterministic** CND + view plan from the manifest (mix:title for titles, j:linkType, picker[type='image'], mainResource→default+fullPage, container→child+card view). | `python3 cnd_emit.py <manifest> --ns <ns> --mixns <mixns> --project <p> --out-cnd … --out-views …` |
| `coverage_probe.mjs` | pre-templatization gap analysis in a **real browser**: JS-render delta, CSS rules/tokens/@media/bg-images/fonts, JS libs+behaviours, all asset requests, fixed/sticky chrome. | `node coverage_probe.mjs <proj> [maxPages]` |
| `reconstruct_probe.mjs` | **the fidelity gate.** Renders **from the local mirror (offline, deterministic — no live/WAF dependency)** when one exists, else the live source; masks everything not in a detected component (visibility:hidden preserves layout), pixel-diffs (pixelmatch), writes a self-contained **`review.html`** (drag-slider source↔reconstruction + diff) AND an interactive **`<slug>.recon.html`** (masked DOM + `<base>` so the site's own CSS/JS load — responsive + hover menus work live; open via the artifact route or `python3 -m http.server`) AND a **`<slug>.overlay.html`** component map (source screenshot + one hover-labelled box per detected component, labelled with the manifest nodeType). GATE = content coverage; pixelSim + diff PNGs = the template/asset gap. | `node reconstruct_probe.mjs <proj> [maxPages] [threshold] [--pages a,b] [--all]` → `reconstruct/{review.html, *.recon.html, *.overlay.html, *.png, reconstruct.json}` |
| `../run_local.py` | **deterministic plan executor** — runs a plan's `Run:`/`PROBE:` lines in dep order, a step passes iff all probes exit 0 (the orchestrator's contract, no agent layer). `--halt-after <step>` = human review gate. | `python3 orchestration/run_local.py <plan> --from <step> --halt-after <step>` |

Plan template: `orchestration/plans/acquia-analyze.plan.json` (crawl → **localize (offline mirror gate)** → semantic → group → cnd → **reconstruct gate**).

---

## 3. The gates (what makes it trustworthy)

1. **Partition gate** (`assemble_manifest`): every group member must be a known candidate id, and every candidate covered exactly once → **hallucination and omission are impossible to pass**.
2. **dup-shape sanitizer** (`assemble_manifest`): within an LLM group, split members whose data-shapes are incompatible (or containers with disjoint child-shapes) → **no grab-bag types**. dup-shape across *distinct roles* is a review WARN, not a hard fail (real sites reuse shapes: Breadcrumb vs CTA).
3. **Stability gate** (`stability_gate`): naming-invariant grouping agreement + cross-cutting presence across N runs.
4. **Mirror gate** (`mirror_probe`, runs BEFORE the fidelity gate): every sample page renders **fully offline** — 0 blocked static-asset requests (only runtime trackers blocked) + stylesheets applied. So the local render is *truly* local, not silently pulling from the source. Mirror-fidelity (offline vs live) reported alongside (acquia: 99.97–99.98%).
5. **Fidelity gate** (`reconstruct_probe`): content coverage ≥ threshold; renders from the local mirror (offline/deterministic); the visual review (`review.html`) is the human approval before templatization.

---

## 4. Agnosticism — SXA fast-path + agnostic fallback

`class="component"` (SXA) is a strong deterministic signal and gets a fast-path. For
non-SXA sites the **recursive altitude finder** carries it: chrome = `<header>/<footer>/<nav>`
+ `region--*` (Drupal); content = the first multi-block row below `<main>`/`region--content`,
stopping at that altitude (deeper nesting = fields/child items). **Titled section = ONE
component** (title + intro + items) — a node carrying its own heading is emitted whole
(`_own_heading`), so section titles are never dropped.

**Hard lesson:** a 3-page hand fixture passed, but real Drupal (acquia.com) exposed a
**BEM-explosion** (2816 instances, 0/3 cross-cutting) because deep `ss-flex-header__…`
nesting made every titled div a "component". The altitude finder fixed it (→ 300
instances, 3/3 cross-cutting). **Always validate agnosticism on a real non-SXA site,
never a toy fixture. The fidelity gate is what catches these gaps.**

---

## 5. DeepSeek V4 Flash

- Endpoint `https://api.deepseek.com/v1`, models `deepseek-v4-flash` / `deepseek-v4-pro` (real). Key + opencode config in `~/.config/opencode/opencode.jsonc`.
- **It is a REASONING model:** ~13k reasoning tokens before the answer → `max_tokens` must be ≥ 16000 or `content` comes back empty. (`group_llm.py` sets 16000.)
- The `migration-orchestrator` engine sends **no model/temperature/seed** to opencode (`opencode_client.send_prompt_async`) — the plan `model` field is decorative; the real model is the opencode config. Reproducibility must come from the **content** (deterministic layer + gates), not the engine. `run_local.py` is the fully-deterministic executor.

---

## 6. Orchestrator specialization (migration profile)

Turn the generic Run→Epic→Story→Step engine into a **migration cockpit** — see
`migration-orchestrator/frontend/MIGRATION_PROFILE.md`. Shipped this session:
- Backend: `gate_type` on `StepState` (set at HALT via `_infer_gate_type`, pushed in SSE); `GET /runs/{id}/artifacts/{path}` (serves `workflow-output`); `POST /runs/{id}/fidelity/rerun`.
- Frontend (React/Tailwind, `tsc`-clean): `components/fidelity/FidelityGate.tsx` (+ `BeforeAfterSlider`), `components/migration/PipelineRail.tsx`, `ComponentModelView.tsx`; wired into `RunDetail.tsx` for migration runs.
- Visual identity pinned to jahia.com: navy `#001932`, azure `#0077bf` / cyan `#00a1e3`, light `#eef2f6`, Plus Jakarta Sans, uppercase+`›` buttons, notched cards. Magenta `#d6217d` reserved for the pixel-diff motif only.

---

## 7. Results (two reference sites)

| | supercar-garage (SXA, 22p) | acquia.com (real Drupal, 18p) |
|---|---|---|
| candidates | 29 content + 3 x-cut | 46 content + 3 x-cut |
| model | 25 types + 3 x-cut + 4 templates | 21 types + 3 x-cut + 5 templates |
| grouping stability | 99% | 95% |
| cross-cutting | 3/3 (top-bar, header-nav, footer) | 3/3 (header, nav, footer) |
| reconstruction (content coverage) | 100% | 99–100% (only orphan = cookie-consent + a11y chrome) |
| pixel fidelity (components-only) | 91–95% | 73–99% (rest = section backgrounds / hero = template job) |
| mainResource / detail pages | — | `acq:article` from `blog_*` cluster (listing `blog` ✓); detail pages: content 100%, pixel 98.5–98.9% |

---

## 8. `mainResource` / detail-page detection — ✅ SHIPPED

Detail pages (blog article, product sheet…) render the **entity node itself** via a
`jmix:mainResource` fullPage template — not a dropped component. Missed, the article
body is modeled as ordinary components and the page can never be pixel-perfect.
Detection is deterministic + agnostic (structure, not vocabulary):

1. **Detail cluster** (`semantic_extract.detect_detail_templates`): a template cluster
   whose pages share a parent path segment `P` (slug depth > 1); **high confidence** if
   `P` is itself a crawled page (the listing/index) → a list/detail pair.
2. **Entity** = a main-position role that is cluster-exclusive (`pages ⊆ cluster`) and
   singular (~one instance per page); its facet family = the shared role stem. CMS
   content-type prefixes are stripped (`ct-article` → `article`) so the bare entity node
   is chosen over its wrappers. Emitted as `detailTemplates[]` in `semantic-candidates.json`.
3. **`assemble_manifest.isolate_main_resources`**: a deterministic lever — the entity
   role becomes its **own** type even if the LLM/shape-sanitizer merged it into a
   grab-bag (e.g. `article` merged with image-containers on a shared hero image). The
   type gets `needsMainResource=true` + a `kind:"detail"` template.
4. `cnd_emit` already turns `needsMainResource` into `jmix:mainResource` supertype +
   `fullPage.server.tsx` view.

Verified on acquia (blog): `tpl_01` → entity `article`, listing `blog` ✓, confidence high
→ `acq:article` (mainResource) + `blogDetail` template. Reconstruction fidelity on blog
detail pages: **content 100%, pixelSim 98.5–98.9%, GATE GREEN**. Byte-stable across runs.

**Entity enrichment (✅):** `assemble_manifest` folds the scalar-content facet shapes
(title / body-richtext / image / link) into the entity's own fields — so `acq:article`
carries `mix:title` + `image` + rich `text` + CTA link itself, not just an image. Container
facets (FAQ, related-content lists) stay separate components placed in the detail template.

## 9. Open items / next

- Junk low-freq roles survive on non-SXA (`ul`, `div`, `js-form-item`) — light noise filter.
- Crawler has **no JS render** — add Playwright render for JS-hydrated sites.
- Then: templatization (step 4) using the diff PNGs as the spec.

## 10. Security

- ✅ **In-code secret removed** — `hybrid-identify.py` no longer hardcodes the OVH key; it now reads `os.environ.get("OVH_API_KEY", "")` (`:173`). Set `OVH_API_KEY` in the environment.
- ⚠️ Live DeepSeek/Xiaomi/OVH keys still live in `~/.config/opencode/opencode.jsonc` (user config, **not** committed to this repo). If any of these keys were ever exposed, rotate them; keep opencode config out of version control.
