# Library-first zoning remediation — plan (2026-07-06)

Rewrite of the zoning remediation around a **library-first** axis, validated against
jahiacom-v3 (`Jahia/jahiacom-v3`, the reference module) and against the real component
distribution of the 5 migrated stacks. Supersedes the "collapse-only" framing in the
`SESSION-2026-07-05` remediation notes; the collapse work survives as Phase 4 (skeleton
tail only). Companion to `LIBRARY-SPEC.md` (the taxonomy) and `MODULARITY-PLAN.md`
(the fidelity↔composability tension, §3).

---

## 0. The two problems this closes (Julian)

1. **A zone must be a pure container of sub-components, never carry HTML.** Measured: 100%
   of emitted `zone` instances on all 5 stacks carry structural wrapper HTML in their
   `skeleton` (avg 472 chars, up to 10 KB on discoverasr). 0 leaked editorial text — it is
   layout markup living as *data* instead of being an `<Area>`.
2. **Over-zoning / contiguous zones.** The bridge maps the source DOM ~1:1 to a zone tree.
   discoverasr: 66 zones/page, depth 10, 1.04 zone-nodes per real component, 194 content-free
   mini-components wedged between contiguous zones. contentful proves clean is achievable
   (4 zones/page, depth 2, 0 walls).

Both share ONE root cause: the bridge reproduces the DOM as skeleton-bearing zones instead
of recognising editorial sections into **authored library components** whose markup lives in
the VIEW (the jahiacom-v3 model).

---

## 1. What jahiacom-v3 actually is (the reference, read from source)

- Each section = a **typed content node with pure editable properties** (`title`, `image`
  weakref) + **typed children** (`+ button (buttonItem)`, `+ * (faqItem)`). **Zero HTML in
  the node.**
- **All markup lives in hand-written JSX views** (`Section.jsx`, per-section views). Content
  is data; HTML is code.
- Pages = fixed templates: a sequence of `<Area allowedTypes={[oneSectionType]}>`
  (`PageHome.jsx` etc.). Chrome = `<Area navbar/footer>` in `MainLayout.jsx`.
- `sectionCustom` = a content-free **layout component** (style / padding / bg / height config
  + `{children}`) — exactly the "content-free layout component with child slots" pattern.

jahiacom-v3 has **no pixel target**, so it has no fidelity↔composability tension. We take its
taxonomy + composition mechanics; we go **one open composition `<Area>`** (the deployed
`lesalondelaphoto` pattern) instead of one-type-per-Area, so contributors compose freely.

---

## 2. Validation — base-library coverage vs the 5 stacks (6232 instances, instance-weighted)

| stack | insts | LIBRARY (authored) | STRUCT (zone→Area) | content-free | rawHtml (fallback) | CUSTOM/gap |
|---|---|---|---|---|---|---|
| contentful | 376 | 54% | 22% | 22% | 0% | 0% |
| acquia | 486 | 60% | 25% | 2% | 11% | 0% |
| liferay | 961 | 54% | 32% | 3% | 9% | 0% |
| supercar | 554 | 48% | 33% | 3% | 15% | 0% |
| discoverasr | 3855 | 33% | 34% | 16% | 15% | 0% |
| **aggregate** | **6232** | **41%** | **32%** | **12%** | **13%** | **~0%** |

**Conclusions:**
1. **CUSTOM/gap ≈ 0%** — the taxonomy already covers ~all types (the bridge's `library_map`
   already names everything as a library type). The gap is NOT missing type names.
2. **41% LIBRARY + 12% content-free could become authored library components now**, and
   **32% structural zones become `<Area>`**. **~13% rawHtml** is the honest irreducible tail
   (AEM/Liferay widgets).
3. **The real gap is wiring + recognizer coverage, not taxonomy:** `library_recognize.py`
   exists and IS wired via `extract_content.py` (`recognize()` at lines 1018/1150), but it
   ships only 3 container recognizers (logoWall / carousel / tabs). No `section`, `cardGrid`
   (as a recognizer), or generic-layout recognizer — the big buckets stay skeleton.

---

## 2bis. Measured chiffrage (2026-07-06)

**(a) Wiring the existing recognizer AS-IS = ~5%.** Over all 2621 container instances
(skeleton + `{{child}}`), `recognize()` converts only 139 (5%): carousel×85, logoWall×32,
tabs×22. Per stack: contentful 38%, acquia 6%, liferay 3%, discoverasr 2%, supercar 2%.
Reason: only 3 recognizers ship; the untapped buckets are `zone` (~2026), `section` (~407),
`cardGrid` (~126, incl. contentful 84 — the bridge *names* them cardGrid but there is no
cardGrid recognizer).

**(b) Generic LAYOUT recognizer (`_recognize_layout`, prototyped + wired count-only).** A
PURE structural wrapper (no own text) with ≥2 block child slots → source-class chain + open
`<Area>`. Real-pipeline measurement (run over actual source nodes, not the skeleton):

| stack | zones | layout-convertible | rate |
|---|---|---|---|
| discoverasr | 1325 | 1319 | **99%** |
| contentful | 130 | 127 | **97%** |

Skeleton simulation (over post-extraction skeletons) was more conservative — authored-
container% 2%→76% (discoverasr), 63%→81% (contentful), 57-72% on acquia/liferay/supercar —
but both agree the layout recognizer is the dominant lever.

**KEY FINDING — the layout recognizer is BYTE-EXACT, OUTSIDE the §3 trade.** A pure wrapper's
only content is its children (in order) + structural tags; an `<Area>` rendering the same
children wrapped in the captured source-class chain reproduces the source byte-for-byte. So
**converting `zone`→`<Area>` fixes P1 (zone carries HTML) with NO fidelity cost.** The pixel
trade in §3 applies only to atom/section library views (card/hero with *imposed* markup), NOT
to the generic layout container. Refusals (own text / single-child / text-run) stay skeleton.

**Caveats:** (1) depth is NOT reduced — nesting becomes nested Areas (P1 fix, not P2); depth
needs chrome→AbsoluteArea + single-child collapse + fusion. (2) Celled/column layouts need a
`columns[N]` view (N Areas), still byte-exact, a Phase-3 view detail. (3) 99%/97% is the
recognizer-acceptance ceiling; real conversion also needs the view + CND + `extract_content`
plan-handling for the `layoutSection` kind (the emit step, staged after this measurement).

---

## 3. The doctrinal decision this forces (owner: Julian)

An authored library view produces the **library's** markup, not the source's exact bytes:

> **byte-exact (0-DOM) and clean library components are mutually exclusive for arbitrary
> source markup — one OR the other, per section.**

Library-first ⇒ trade byte-exact for editability, arbitrated **per section by a pixel gate**
(not a byte gate): confident library match + rendered within a pixel threshold of the source
→ library component; else → skeleton (byte-exact). **0-DOM stops being a global invariant and
becomes a per-section choice** (MODULARITY-PLAN §3 tension made explicit).

**Scope (refined by §2bis):** this trade applies ONLY to atom/section library views with
*imposed* markup (card/hero). The **generic layout container** (`zone`→`<Area>`, ~99% of
zones, byte-exact by construction) needs **no trade** — ship it unconditionally. So the
pixel-gate decision gates Phase 1c (atom/section views), not the layout conversion.

---

## 4. Target model (= jahiacom-v3, more flexible)

- Page = `Layout` + chrome in **AbsoluteArea** (`<Area navbar/footer>`, like `MainLayout.jsx`)
  + one open **`<Area name="main" allowedNodeTypes={OPEN_PALETTE}>`** (deployed
  `lesalondelaphoto` pattern, LIBRARY-SPEC §3).
- Section = **authored library component**: typed props + `<Area>`/`<RenderChildren filter>`
  for children. **0 HTML in the node.**
- Atoms = library (button/card/image/richText/heading/logo…).
- `rawHtml` skeleton = **shrinking** fallback (13%); every use logged as a library gap that
  feeds library growth.

---

## 5. Phases

| Phase | Action | Existing asset |
|---|---|---|
| **0** | Telemetry: emit per-stack `library% / struct% / cfree% / rawHtml% / layoutConvertible` + over-zoning (zones/page, depth, zones÷components) to the manifest = frozen baseline + gap KPI | **done** (`mergeBacklog.layoutConvertible/zoneInstances`) |
| **1a** | Wire the 3 existing recognizers as-is (logoWall/carousel/tabs) | already via `extract_content` — **~5%**, marginal |
| **1b** | **Generic LAYOUT recognizer → `zone` = byte-exact `<Area>`** — the dominant lever (**99%/97% of zones**), NO fidelity trade. `_recognize_layout` prototyped + wired count-only; emit-conversion needs the view + CND + `extract_content` `layoutSection` handling | recognizer **written** (`library_recognize._recognize_layout`) |
| **1c** | Author `cardGrid` + `section`/atom recognizers/views with *imposed* markup — **pixel-gated (§3 trade)** | base-library template |
| **2** | **Chrome → AbsoluteArea** (navbar/footer), like `MainLayout.jsx` → kills discoverasr's 76% chrome-per-page | known pattern (jahia.md r.15) |
| **3** | **Author/complete the library VIEWS** (jahiacom-v3-style, `<Area>`+`<RenderChildren>`) + wire the layoutSection emit | base-library template exists; views to finish |
| **4** | Collapse residual structural nesting (fusion + content-free wall absorption) — the **skeleton tail + depth (P2)** | design done (SESSION-2026-07-05) |

**Order (value/risk):** 0 (measure, done) → 2 (chrome, big gain, no trade) → **1b (layout→Area,
byte-exact, no trade — the dominant lever)** → 3 (views) → 1c (atom/section views, pixel-gated)
→ 4 (tail + depth). The §3 pixel-gate go is required only before **1c** — 1b needs no trade.

---

## 6. Guards (anti-overfit — non-negotiable)

- **`rawHtml%` per stack = library-gap KPI:** contentful must stay **0%**, discoverasr/liferay
  must not rise, `library%` must rise. Wired into `test_zone_detect.py` (5-stack replay).
- **Per-section pixel gate** = the fidelity↔modularity decision, audited at the model gate
  (0-DOM never silently abandoned).
- **Anti "God object"** (LIBRARY-SPEC §0): numbered `title1..N` props → **child nodes**;
  `richtext` bodies; `mix:title` titles.
- **Recognizer keys on structure/geometry, never a framework class** (anti-overfit).

---

## 7. What already exists (do NOT rewrite)

`LIBRARY-SPEC.md` (design), `library_recognize.py` (recognizer), `install_base_library.py` +
`templates/base-library/` (types + tokens), `lesalondelaphoto` (deployed `<Area>` views),
`MODULARITY-PLAN.md` (the tension). Net work = **recognizer→bridge wiring + view authoring +
per-section pixel gate + gap telemetry** — not reinvention.
