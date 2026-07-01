# Probe scripts — the verification library

All probes live in this directory and run from the repo root. A step is done only
when every `PROBE:` line in its acceptance criteria exits 0 — the probes are the
contract, not the agent's word (AGENTS.md §3).

If a probe is wrong for a project, fix the probe script (it is versioned) rather
than skipping verification.

All under `orchestration/probes/`, run from repo root:

| Probe | Proves |
|-------|--------|
| `connect.sh <project_path>` | Jahia reachable + creds valid (HTTP 200/400) |
| `analyze.sh <project_path>` | `component-manifest.json` + `content-data.json` exist, non-empty |
| `build.sh <project_path>` | `yarn build` exits 0 |
| `assets.sh <project_path>` | `static/` has CSS and Layout references a stylesheet |
| `cnd.sh <project_path> <namespace>` | build clean + namespace in `definitions.cnd` + en/fr `.properties` |
| `component.sh <project_path> <name>` | named component source exists + build clean |
| `component-validate.sh <project_path> <ns> <ComponentDir> [page] [site] [lang]` | **FULL per-component gate** (see 5a) — source, **no duplicate default-view**, CND patterns (that component only), en+fr i18n for every type/property, build, deploy, bundle ACTIVE, and a **non-home page renders 200** (+ clean engine log) |
| `cnd-patterns.sh <project_path \| one.cnd> [ns]` | CND modelling rules (mix:title, jmix:tagged/categorized, linkTypeInitializer, weakref). Pass a single `.cnd` to lint just one component |
| `templates.sh <project_path>` | Layout has >=2 `AbsoluteArea` (header+footer) |
| `deploy.sh <project_path>` | build + `yarn jahia-deploy` succeed |
| `content.sh <project_path> <site> <lang> <page1,page2,...>` | each page's LIVE `<main>` text > 400 chars |
| `fidelity-all.sh <project_path> <site> <lang> <pages\|@sitemap>` | **FIDELITY GATE (the wired one)** — loops `fidelity-live` over every page, pairing each with its captured `.reference/captured/<slug>.html`; FAILS on the first page materially below its reference, and FAILS if NO page had a capture (capture-reference never ran). The per-page fidelity gate used in `step_visual_diff` + the reviewer |
| `fidelity-live.sh <referenceSrc> <live_url>` | **JS-rendered fidelity (single page)** — renders the local page AND a reference (the captured `.reference/captured/<slug>.html`, or a URL) in headless Chromium and diffs **sections + listing/card counts + facet values** (warns on image shortfall / reorder). Called by `fidelity-all`; use directly to debug one page. Saves a ref-vs-local screenshot pair |
| `fidelity.sh <reference.mhtml\|html> <live_url> [min_pct]` | **DEPRECATED** (curl, static, headings-only) — passed visually-wrong pages once JS ran. Superseded by `fidelity-all`/`fidelity-live`; kept only as a no-browser fallback |
| `render-truth.sh <url> [--edit]` | **OBSERVABLE RENDER** (headless) — fails on broken images (`naturalWidth=0`), content stuck at `opacity:0` after scroll, collapsed shared regions, playerless video. Saves a screenshot. `--edit` for the Page Builder frame |
| `render-all.sh <project_path> <site> <lang> <pages\|@sitemap>` | render-truth over EVERY page — the per-page render gate (run at each page creation, not at the end) |
| `publish-parity.sh <project_path> <site> [langs]` | **PUBLISH COMPLETENESS** — every weakref'd asset resolves in LIVE + every translation present in EDIT is published (catches unpublished DAM + the `languages:[...]` gap) |
| `edit-frame.sh <project_path> <site> <lang> [page]` | Page Builder edit frame LOADS + the page has editable area markers. **FAILS only** on "Page Builder didn't load" or "no editable areas". Blank nav/footer = **WARN, not fail**: `jmix:hiddenType` on those singletons hides them from the picker + blocks inline selection (correct), but they render in **live always** and in **edit once the AbsoluteArea has child content** (AbsoluteArea-needs-children). A blank shared region in edit ≠ defect — populate it. Do NOT remove `jmix:hiddenType` to satisfy this probe. |
| `no-stub.sh <project_path> [namespace]` | **NO STUBS** — every `*.server.tsx` view emits real markup (no TODO/placeholder/null-only shells), and every CND type has a registered view. Catches the loop generating shells it never fills (the supercar 29/32-stub fiasco) |
| `components-all.sh <project_path> <namespace>` | **PER-COMPONENT COMPLETENESS** — loops EVERY component dir and FAILS naming any that is stubbed, viewless (CND but no `*.server.tsx`), or missing an en/fr label for its type or an own-namespace property; builds the module once at the end. The "fail at once, name the component" batch gate for the components step — strictly stronger than `build.sh`+`no-stub.sh`. Does NOT deploy (use `component-validate.sh` per component while iterating) |
| `dup-shapes.sh <project_path> [namespace]` | **REUSE/VIEWS** — fails when two CND types share the same property shape (they should be ONE type + additional views, AGENTS §2b). Catches markup-driven type duplication at the source |
| `cnd-review.sh <project_path>` | **CND quality** (agentic `check-cnd.mjs`) — best-practice antipatterns with file:line; complements `cnd-patterns.sh` |
| `site-review.sh <project_path> <site> <lang> <pages\|@sitemap>` | **a11y + SEO** (agentic `review-pages.mjs`, axe-core) — scores each page, fails on critical/serious a11y or missing SEO baseline |
| `artifact.sh <file> [forbidden_regex]` | output file exists (and lacks a forbidden pattern, e.g. `critical`) |

> `render-truth`/`render-all`/`publish-parity`/`edit-frame` come from the migration-harness retro; `cnd-review`/`site-review` are agentic gates (`check-cnd.mjs` / `review-pages.mjs`) — see `.agents/AGENTIC-SYNC.md`. For CND authoring, prefer the `jahia-cnd-author` skill (loads the 9 `references/cnd-*.md` docs) and validate with `cnd-review.sh` until clean.

If a probe is wrong for a project, fix the probe script (it is versioned) rather

Newer gates not yet in the table above:

| Probe | Proves |
|-------|--------|
| `contract.sh <project_path> <step_id>` | **INTER-STEP DATA CONTRACT** — every file the step consumes exists non-stub at its canonical path (naming the upstream producer if missing) and every file it produces was delivered. Table + patterns in `orchestration/lib/contract.py` |
| `component-one.sh <project_path> <ns> <ns:type\|Dir>` | **ONE component** complete (locates the dir by nodeType): source pairing + no-stub + en/fr i18n + cm view. The per-component-story gate in generated plans (cheap: no build/deploy) |
| `mainresource.sh <project> <site> [locale]` | every declared mainResource contentFolder exists, is populated + published, and NO mainResource node lives outside a contentFolder |
| `startnode.sh <project> <site> [locale]` | every mainResource listing query's startNode resolves to a jnt:contentFolder (never a page, never empty) |
