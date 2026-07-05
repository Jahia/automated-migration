# Zone / Component Identification — the fine-signal-first approach (P6.4)

Proven by spike on 5 locally-crawled corpora (discoverasr, contentful, supercar, acquia, liferay),
analysis-only, **zero Jahia / zero deploy / zero LIVE**. Spike code lives in the session scratchpad
(`zone_spike.py` v1 structural → `zone_spike2.py` scope+auto-knee → `zone_spike3.py` fine-signal-first;
`signal_probe.py` / `signal_norm.py` = the signal-richness measurements; `gen_zoning2.py` = the
observability artifact). This doc is the durable synthesis; promote the spike into `orchestration/lib/`
once the approach is accepted.

## 0. Verdict

Identify zones/components from the **DOM's own signals**, strongest-first, not from a synthetic
structural fingerprint. Recurrence + DOM nesting then give the hierarchy. Measured across 5 sites:
**component identity + containment + records are solid and deterministic**; **cost scales with the
component vocabulary (~50–150 types), not page count**; the **residual hard part is template
clustering**, which does NOT block the two high-value tiers.

## 1. Why not a structural hash (the pivot)

Iteration 1–2 stripped every attribute and hashed each subtree to a 64-bit structural simhash, then
clustered on Hamming distance. It worked but was **noisy**: the knee threshold was unstable, and the
signal was lossy/synthetic (two very different blocks with the same tag skeleton collide). Julian's
critique was correct: we were **discarding the deterministic fine signal**. Measured (`signal_norm.py`),
every site carries a rich, recurring, semantic vocabulary:

| site | recurring class stems (≥3 pages) | explicit markers |
|---|---|---|
| discoverasr (AEM) | 587 | `cmp-list__*`; `data-adobe-cta/-heading/-link` name CTAs/headings/links |
| contentful (Next.js) | 356 | **`data-component="basic_card"/"navigation"/"title"`** — declares its taxonomy |
| supercar (Jahia/SXA) | 139 | `component`, `field-*` — CMS field names in clear |
| acquia (Drupal) | 291 | `field--name-*`, `block-*`, `data-entity-type/-uuid`; **ARIA `banner/contentinfo/main/navigation`** |
| liferay | 587 | `lfr-`/`osb-` under Bootstrap utility noise |

The synthetic hash **masked** this — it even made contentful (the most explicitly-structured, via
`data-component`) look like the hardest site. The structural hash is kept, but **demoted to a fallback**.

## 2. The generic mechanism — a signal hierarchy (determinism decreasing)

Every element gets a **component identity key** from the strongest signal it carries:

| Tier | Signal | Gives | Example key |
|---|---|---|---|
| **L0** | explicit markers: `data-component`, `data-testid`, `itemtype` (microdata) | component identity | `cmp:basic_card` |
| **L1** | ARIA landmark `role` / HTML5 semantic tag | scope boundary | `role:banner`, `tag:footer` |
| **L2** | framework class stem: `cmp-`, `field--name-`, `paragraph--type-`, `block-`, `lfr-`, `component`/`field-` | component/field id | `cls:cmp-teaser` |
| **L3** | recurring semantic class stem (CSS-module hash stripped, utility-filtered, doc-freq ≥3) | component id | `cls:asr-slide-item` |
| **L4** | structural tag-shape hash | anonymous fallback | `struct:…` |

The **generic, site-agnostic** rule: *a normalized non-utility class stem / marker that RECURS is a
component identity; DOM nesting gives containment; repeated same-key siblings are records.* Framework
prefixes (`cmp-`/`field--`/`lfr-`) are a **confidence prior, never a requirement** — nothing is
hard-coded per CMS. Normalization: strip CSS-module hash suffixes (`nav_item__XAu2F`→`nav_item`),
filter utility vocabulary (Bootstrap `col-`/`d-flex`/`bg-`, Tailwind variant classes `lg:`/`hover:`).

**Structural gate:** an L3 key is a component boundary only if it wraps a real block (median subtree
≥4 nodes) — leaf text-style spans (`font-body-1`) are not components.

## 3. Scope model (Julian's absolute / zone / component / sub-component / record)

Derived after detecting & subtracting **site chrome first** (the recurring lesson — chrome swamps
everything otherwise):

- **ABSOLUTE zone** → `AbsoluteArea`: key on ≥90 % of pages, OR an ARIA landmark (`banner`/`contentinfo`/`navigation`). Deterministic; no clustering needed.
- **TEMPLATE zone** → `Area` the template places: key on ~all pages of ONE template cluster, ~0 % elsewhere.
- **COMPONENT** → page-level contributable unit (the residue).
- **RECORD** → ≥3 repeated same-key siblings = list items / carousel slides / cards.
- **SUB-COMPONENT**: DOM nesting — a component's nearest-anchor children (e.g. `Asr Content Slider ↳ Scroller Wrapper ↳ Asr Slide Item`; `Card ↳ Case Study Card`). BEM `block__element` and child nodes give this for free.

## 4. Q1 — how is it generic?

The detection mechanism (recurring normalized stem/marker = identity; nesting = containment;
sibling-repeat = record) is **framework-agnostic**. Per-site adaptation is **data-driven, not coded**:
a **regime** is auto-detected from the corpus — *explicit markers* (contentful), *framework-semantic
classes* (supercar/liferay), or *recurring classes / structural fallback* (measured per site). No
per-CMS recognizer is written; the framework prefix list only boosts confidence. Genuinely
anonymous/hashed regions fall through to L4 (structural) — graceful degradation, never a block.

## 5. Q6 — scaling to 10 / 200 / 10 000 pages

**The component vocabulary saturates** (measured — types vs pages, `--scaling`):

| site | 1p | ¼ | ½ | ¾ | full | new types in last quarter |
|---|---|---|---|---|---|---|
| discoverasr | 58 | 66 | 71 | 71 | 72 | **+1** |
| contentful | 50 | 89 | 114 | 117 | 117 | **+0** |
| supercar | 38 | 46 | 49 | 52 | 54 | +2 |
| acquia | 10 | 12 | 13 | 13 | 13 | +0 |
| liferay | 57 | 118 | 137 | 144 | 150 | +6 |

By ~page 16 almost no new component types appear. Therefore:
- **Detection** = one streaming pass, O(nodes), embarrassingly parallel per page. 10 000 pages = 10 000 independent parses; hold only the compact per-key aggregate, discard trees.
- **LLM/DeepSeek naming** = O(#distinct types ≈ 50–150), **flat in page count**. 10 000 pages cost the *same naming* as 20. This is the killer scaling property.
- **Template clustering** (the only O(pages²) step): fine at 200; at 10 000 use MinHash/LSH banding over the arrangement signature (sub-quadratic), or bucket by URL-path pattern first.
- **Naming/representative sampling**: only K representatives per type are needed, not all instances.

## 6. Q5 — naming zones/components

- **Deterministic (the majority):** the identity key IS the name. `data-component="basic_card"`→"Basic Card"; `cmp-teaser`→"Teaser"; `field--name-field-related`→"Related"; `block-footer-menu`→"Footer Menu". A `humanize()` (strip framework prefix, split `-/_`, title-case) covers L0–L2 and good L3.
- **DeepSeek (the tail):** cryptic/anonymous keys (L4 structural, or opaque L3 like `Cm`, `Rah Static`) where `humanize()` gives a bad editor label. DeepSeek proposes an editorial name + `ui.tooltip` + base-library-type mapping + confidence, from the representative HTML + text + parent/child keys.
- **Bright line (P5.6):** naming produces **editor-UI labels only** — never site content, never invented structure. Editor labels/tooltips ARE generable; final-site content is NOT. Low-confidence → defer to the human gate.

## 7. Q3 — DeepSeek's high-value role

DeepSeek does the **semantic layer on top of deterministic detection** — never detection, never content:
1. **Name** anonymous/cryptic components (L4/opaque L3) — editor labels + tooltips.
2. **Map** detected component types → base-library types (is this a `carousel`? a `cardGrid`? a `richText`?).
3. **Tie-break** the ambiguous scope/variance cases (template-fixed vs zone; repeatable list vs fixed layout; list vs one text-run per rule §24) — pre-digesting the decision.
4. **Pre-digest** the zoning map into a human-readable review bundle for the gate.

This is the P5.6 bright line + the P5 charter made concrete: the engine + deterministic detection do the
structure; DeepSeek adds cheap semantics at bounded cost (O(vocabulary)); it never touches fidelity/content.

## 8. Q4 — my role when piloting the orchestrator

I do NOT detect or name per site (deterministic engine + DeepSeek do). I:
- **Decide at genuine forks** DeepSeek flags (a low-confidence naming, an ambiguous template split, a novel regime).
- **Handle exceptions** — a site where fine signals fail and the L4 fallback is noisy: decide whether to accept lower composability or invest.
- **Extend the generic mechanism** when telemetry shows a *systematic* gap (a new utility vocabulary to filter, a framework prefix to add as a prior) — generically, never per-site overfit.
- **Review the observability artifact** at the gate before any module is built, and adjudicate what Julian/the human should see.

Engine executes deterministically → DeepSeek pre-digests decisions → I decide at bifurcations → human (Julian) validates the zoning map before build.

## 9. Q7 — observability for human validation

The **zoning-map artifact** (`gen_zoning2.py` → published Artifact) shows, per site: regime + DOM
coverage + template clusters; and per scope (absolute/template/component/record) the detected components
with **signal tier badge** (so the human sees *what* drove each identification and how much to trust it),
metrics (pages/instances/sibling-repeat/variance), a content sample, and the **sub-component tree**. Plus
the vocabulary-saturation sparkline (the scaling proof). This is a **cheap artifact reviewed BEFORE any
CND/view is generated** — being wrong costs a map edit, not a re-migration. The gate: DeepSeek pre-digests,
the human confirms/edits the decomposition, THEN the build proceeds.

## 10. Measured results (5 sites)

| site | regime (auto) | DOM cov | absolute | template | component | record |
|---|---|---|---|---|---|---|
| contentful | explicit markers | 100 % | 6 | 12 | 14 | 12 |
| discoverasr | recurring classes | 100 % | (chrome) | — | 14 | 12 |
| supercar | framework-semantic | 99 % | 6 | 1 | 14 | 2 |
| acquia | recurring classes | 100 % | 3 | 1 | 13 | 4 |
| liferay | framework-semantic | 100 % | 4 | 0 | 14 | 14 |

(“component/record” counts are the top-N surfaced, not exhaustive.) contentful is the showcase:
`data-component` yields `Basic Card`, `Case Study Card`, `Card With Image`, `Copy Block`, and the
carousel `Swiper Wrapper ↳ Swiper Slide` — named, nested, deterministic.

## 11. Honest limits

- **Template clustering is the residual hard part.** A mature CMS reuses one component palette on every
  page, so "which components appear" barely separates templates; even structural arrangement is close
  between pages. Best signal = multi-signal (arrangement simhash + URL-path pattern + main-region spine)
  + a human glance. The two high-value tiers (absolute zones, components/records) do NOT depend on it.
- **Regime guard.** The auto-regime label is crude (discoverasr has `cmp-*` + `data-adobe` yet leans L3);
  refine, but it's directionally right and drives the fallback decision.
- **Utility-filter tail.** New utility vocabularies leak occasionally (fixed Tailwind `lg:`/`font-` this
  round). Telemetry-driven, not guesswork.
- **Verification.** Detector scope-assignments were adversarially cross-checked against the real DOM (see
  the verification section / gate); some misclassifications are expected and are exactly what the human
  gate catches.

## 12. Next

1. Promote the spike into `orchestration/lib/zone_detect.py` (streaming + LSH template clustering).
2. Wire the regime detector + fine-signal identity ahead of the existing structural segmentation (fallback).
3. Emit the zoning map as the **pre-build gate artifact**; DeepSeek pre-digest + human confirm.
4. Map confirmed component types → base-library types; the existing recognizers become renderers.
5. Keep the scope-relative + variance + verbatim-fidelity framework from P6 on top of the new signal.

## 13. Adversarial verification cycle (the discipline that caught the optimistic first cut)

The first v3 output *looked* good; an adversarial pass (independent agents cross-checking every
scope assignment against the real crawled DOM) returned **WEAK on both discoverasr and contentful**
and found concrete defects — exactly the optimistic-narration trap. The findings and the fixes:

| Verification finding | Fix |
|---|---|
| `cls:page` (the `<body>`, 6858 desc) / Next.js `__className` shell emitted as an ABSOLUTE zone | ROOT-WRAPPER guard — median subtree ≥55 % of page ⇒ scope `ROOT`, never a zone |
| `asr-section-rich-text` (editorial cookie/intro body copy) marked chrome purely by ≥90 %-of-pages ubiquity | site-chrome now requires **low variance OR high link-density** — varying prose is excluded |
| the REAL footer/nav (`asr-global-footer`, `asr-main-navigation`) ABSENT from output | `emit` treats root-wrappers as **transparent** so their chrome children surface at top level |
| `role:navigation` = the breadcrumb, mislabeled as main nav | nav is chrome only if link-dense (`ld≥0.5`) |
| ubiquitous LEAF primitives (`Button`, empty `grid_helper`, `card_wrapper_arrow`) as zones | a zone must be a **content-bearing container** (medsize≥6 + has text) |
| Tailwind `lg:col-span-8` / positional `absolute`/`root` leaked as component identities | util filter: any `:`-variant class + positional/plumbing words |

After the fixes, **ABSOLUTE = real chrome on all 5 sites** (contentful: Bars/Navigation/Footer;
discoverasr: Main-Navigation/Top-Menu/Mobile-Menu/cookie-Dialog; acquia: Menu/Navigation/Contentinfo;
supercar: Nav/Header/Footer; liferay: Header/Footer/Contentinfo). RECORDS were verified ACCURATE in
the first pass (sibling counts confirmed against the DOM). **Lesson: identity + records were right
from the start; SCOPE classification + emit-filtering were wrong and only an adversarial DOM
cross-check exposed it — pixel/console output never would have.**

## 14. Naming demonstration + the DeepSeek prompt spec

Deterministic `humanize()` covers L0–L2 and good L3. The tail (cryptic/opaque keys) is DeepSeek's job:

| Bad deterministic name | Proposed editor name | Library type | Why |
|---|---|---|---|
| `Cm` (`cls:cm`) | Policy Section | richText | truncated stem; sample = cookie-policy prose, sib=6 |
| `Rah Static` | *(drop)* | none | `react-animate-height` wrapper — transparent, no identity |
| `Display None` | Booking Search (hidden) | section | CSS utility leak; child = booking modal |
| `Table Condensed` | Date Picker Calendar | none | script-driven daterangepicker (rule 29 — not contributor content) |
| `Aem Gridcolumn` | Content Column | gridRow | AEM layout plumbing (rule 21); holds real components |
| `Asr Carousel Holder` | Banner Carousel | carousel | vendor stem; children = rotating banners |
| `Asr Slide Item` | Article Card | card (in cardGrid) | dated article teasers repeating (rule 24) |
| `__className_e71207` | Page Shell | none/root | Next.js hashed root wrapper |

## 15. Rebuild bridge — status, honest blocker, and plan (2026-07-05)

**Done & verified:** detector promoted to `orchestration/lib/zone_detect.py` (+ `orchestration/tests/
test_zone_detect.py`, all green — a real bug was caught by the tests: RECORD must be classified before
TEMPLATE). All 3 target sites RE-INDEXED with the promoted lib into the fine-signal component model +
base-library type mapping (`library_map`). Readiness (deployed `asr:*` library = all 18 types present):

| site | component+record types | deterministically mapped (conf≥.5) | need DeepSeek/human |
|---|---|---|---|
| discoverasr | 28 | 13 | 15 |
| contentful | 29 | 17 | 12 |
| acquia | 19 | 10 | 9 |

**NOT executed — the Jahia rebuild — and WHY (honest).** Loading the new model into Jahia needs a
bridge `zone_detect model → content-load.json`. Inspecting `load_content.py` (1088 lines) + the base
library shows the bridge is a multi-hour build, not a ~1h one, for a *fidelity-safe* result:
- The loader expects the rich P2.5-D schema (`type_map`, `manifest`, per-node skeleton + slot mixins,
  media weakrefs, links) — essentially `extract_content.py`'s emission, but driven by zone_detect
  boundaries instead of vision segmentation.
- **The base-library views render TYPED FIELDS, not a generic verbatim skeleton** (Card → `props.body`,
  RichText → `props.body`, etc.). So emitting `{type: asr:card, skeleton:<html>}` would render empty —
  fidelity broken. A fidelity-safe modular load requires EITHER the field-lifting machinery (each node
  carries its verbatim skeleton + lifted fields, self-checked byte-exact per rules 22-26) OR a universal
  verbatim-skeleton fallback added to every base-library view.

Per doctrine (don't leave craters; verify against reality; fidelity over completeness; no fake "done"),
**the 3 working Jahia sites were NOT deleted** — deleting them without a proven rebuild would leave
Jahia worse (3 sites gone, nothing fidelity-safe to replace them). The re-index (the new *index*) is
complete; the Jahia rebuild is STAGED.

**Rebuild plan (next):**
1. Add a universal **verbatim-skeleton fallback** to the base-library views (render the node's captured
   `skeletonOrig` when typed fields are empty) — makes any mapped type fidelity-safe by construction.
2. Write `zone_to_contentload.py`: per page, walk the zone_detect tree, emit one instance per anchor
   (`type` = `library_map` result or `rawHtml`; `parent` = containment index; `skeleton` = outerHTML;
   records → child instances), matching the `load_content` schema + a `type_map` for `asr:*`.
3. DeepSeek pass over the conf<0.5 tail (name + map) before emit; human confirms the zoning map.
4. Per site, then: `deleteSite` + uninstall module → `create_site.sh` → `install_base_library` →
   `create_pages` → `load_content --clean` (EDIT-only) → verify EDIT preview (fidelity + G6a editability).
   Delete each site only immediately before its rebuild.

## 14b. DeepSeek naming-prompt spec

**DeepSeek naming-prompt spec** (bright line — P5.6): the layer sits entirely on the editor-UI side.
It outputs the label an editor reads + a tooltip + a mapping into ONE existing base-library type; it
NEVER writes/translates/invents site content (source markup stays verbatim in the skeleton) and NEVER
invents structure. System-prompt guardrails: (1) name editor UI only, treat all text as evidence not
output; (2) never invent structure; (3) map to exactly one of `heading|richText|card|cardGrid|
carousel|logoWall|tabs|accordion|section|gridRow|none`; (4) weak/ambiguous ⇒ `defer_to_human=true`,
`confidence≤0.4`; (5) labels are 1–4 plain words, Title-Case, no vendor prefixes/hashes/CSS-utility/
framework names. Per-component inputs: `key`, current `humanize` name, `tier`, `scope`, page-coverage,
sibling-repeat, representative text sample, parent key, child keys. Output: `{name, tooltip,
library_type, confidence, defer_to_human}`. Cost = O(#distinct types ≈ 50–150), flat in pages.
