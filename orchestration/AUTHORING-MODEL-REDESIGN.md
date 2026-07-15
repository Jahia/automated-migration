# Authoring-Model Redesign — from faithful-clone to a usable Jahia module

**Status:** proposal (2026-07-15). Written after the SingPost run went fully green on
every fidelity gate yet produced an authoring-hostile module (see "Evidence" below).

---

## 1. The problem, stated plainly

The harness is **fidelity-first**. Every producing step captures each page region as
verbatim markup (`skeletonOrig` + a handful of lifted `{{f:}}` fields), and **every gate
measures reproduction**:

| Gate | File | Measures |
|---|---|---|
| partition | `probes/partition.py` | every `<body>` child emitted, nothing dropped |
| component-coverage | `probes/component_coverage.py` | % visible text inside *a* typed instance |
| contribution (G1) | `probes/contribution.py` | % visible text lifted into *a* field |
| compose | `lib/compose_probe.py` | content-load re-composes **byte-identically** to the mirror |
| reconstruct/fidelity | `lib/reconstruct_probe.mjs` | components reproduce source **pixels** |
| ground-truth | `lib/groundtruth_probe.mjs` | live Jahia vs source mirror, pixel diff |

None of these measure **authoring quality**. A run can be 100% green and still be
unusable, because "looks identical" and "is a good Jahia component model" are different —
often opposed — goals. SingPost is the proof.

### Evidence (SingPost, `projects/singpost`, as generated)

- **40+ one-off types** (`sgp:fulfilmentBanner`, `sgp:marketingDataSolutions`,
  `sgp:revenueOpportunitiesCta`, …), each a frozen HTML skeleton — not reusable archetypes.
- **Generic slot fields** `contribBody2…body9`, `image2…imageN` with **no resource-bundle
  labels** → editors see raw `body3`. Content dumped as richtext, not semantic fields.
- **Images embedded in richtext** `body*` (via `semantic_extract.lift_bodies`) in addition
  to the weakref `contribImage` mixins → unmanaged images in copy.
- **`jmix:mainResource`: 0 uses.** News / media / press baked into page skeletons instead
  of structured content in a contentFolder with listing + detail pages.
- **Navigation is frozen richtext** (`sgp:siteHeader.body`), not a Navigation Menu reading
  the `jnt:page` tree via `getChildNodes`.
- **Links: 3 `j:linkType` fields in the whole module**; every other link is a frozen
  `href` in skeleton markup — not editable.
- **`mix:title`: 0 uses.**
- **Cookie consent migrated** as chrome and rendering — it should never be migrated.
- **"Nested components" are richtext slots**, not real child nodes an editor can
  add/remove/reorder.

Contrast with **`mcpShowcase`** (hand-built, in this workspace) — the reference for what
good looks like: semantic components, governed areas, `jmix:mainResource` articles,
`linkTypeInitializer` on every link, weakref images, resource bundles with tooltips,
tree-driven nav. The automated migration produces the near-opposite on every axis.

---

## 2. The principle shift

> **Stop reproducing the source DOM. Start recognizing the source's intent and re-express
> it as clean Jahia content.**

Faithful pixel cloning is a *different product* from a migration. The harness should target
an **editable Jahia module** whose styling comes from an imported **theme**, accepting
pixel drift, rather than freezing per-page HTML to win a pixel diff.

Concretely, every rule already written in `CLAUDE.md` / `.claude/rules/jahia.md` (mix:title,
`jmix:mainResource`, `linkTypeInitializer`, weakref images, jmix:list children,
tree-driven nav, resource bundles with `ui.tooltip`, no hardcoded visitor text) becomes an
**enforced output contract**, not advice the migration ignores.

---

## 3. Target output contract (what "done" means)

For each migrated page, the module must satisfy:

1. **Bounded archetype library.** Every region maps to one of ~12–20 archetypes
   (hero, mediaText, cardGrid+card, accordion, tabs, banner/CTA, statsRow, articleList,
   article (mainResource), navigation, footer, richTextSection). `rawHtml` passthrough is a
   **failure signal**, not a resting place.
2. **Semantic fields, labelled.** Each archetype has a fixed CND with *named* fields
   (`title`, `subtitle`, `image`, `cta`, …) — never `body2…bodyN`. Every type and field has
   an EN + FR label and `ui.tooltip`.
3. **Real child nodes.** Repeating structures (cards, slides, FAQ items, stats) are
   `jmix:list, jmix:renderableList orderable` containers with typed child nodes.
4. **`jmix:mainResource` for content collections.** Articles / news / press → mainResource
   types in a `jnt:contentFolder`, surfaced by a `jcrQuery` listing + a detail template.
5. **Links via `linkTypeInitializer`.** Every contributor link is `j:linkType`
   (internal/external/none) + `j:linknode`/`j:url` injected — zero frozen `href`.
6. **Images via DAM weakref.** Every image is uploaded to the DAM and referenced by weakref
   (`< jmix:image`); zero `<img>` in richtext.
7. **Navigation from the page tree.** One `ns:mainNavigation` reading `getChildNodes` on the
   home page, 3 levels deep. Zero hardcoded nav markup.
8. **Chrome policy.** Header/footer are editable shared components in absolute areas.
   Consent/analytics/tracking/alert overlays are **dropped**, not migrated.
9. **Theme, not frozen markup.** Source CSS imported + tokenized as a site theme; components
   render styled from the theme, not from per-page skeleton bytes.

---

## 4. Defect → root cause → change (traceable)

| Defect (SingPost) | Root cause (file) | Change |
|---|---|---|
| 40+ one-off skeleton types | `segment2manifest.py` mints a type per distinct region name | Map regions to a **fixed archetype library**; a region that doesn't match an archetype is a coverage failure, not a new type |
| `body2…body9` slots, no labels | `extract_content.emit_container_live` / `contribBody*` mixins | Replace generic slots with archetype **semantic fields**; every field emitted with a label+tooltip into `.properties` at emit time |
| Images in richtext | `semantic_extract.lift_bodies` keeps `<img>` in body runs | Extract `<img>` to DAM + weakref field **before** body lift; strip images from richtext |
| No `mainResource` | `segment2manifest` has `detailTemplates` detection but never emits mainResource types | Wire detail detection → emit `jmix:mainResource` type + contentFolder + `jcrQuery` + detail template |
| Nav frozen in richtext | header captured as skeleton chrome (`step_nav` secondary) | Make `ns:mainNavigation` (tree-driven) the **only** nav; never store nav markup as content |
| Links not editable | skeleton keeps verbatim `href` | Map every `<a>` in a semantic field to a `j:linkType` child/field |
| `mix:title` unused | types extend only `jnt:content, nsmix:component` | Archetypes with a heading extend `mix:title` |
| Consent migrated | `reconstruct_probe`/extractor treat consent as ignorable chrome **kept** | **Drop** consent/analytics/tracking subtrees in extraction (a drop-list), not area-flag them |
| Nested items are slots | item-lift stores items as `contribBody*` on a skeleton | Emit items as real typed child nodes under a `jmix:list` container |

---

## 5. Pipeline changes, stage by stage

The stages stay; their *output target* changes.

- **Segmentation (`segment_probe.mjs`, adjudication).** Keep — region detection is still the
  right first step. Add an **archetype label** to each region (vision already names them;
  constrain the vocabulary to the archetype library, adjudication picks from it).
- **Manifest (`segment2manifest.py`).** Rewrite the core: instead of "one nodeType per region
  name," resolve each region's archetype → a **library CND template** with fixed semantic
  fields + childType. Emit resource-bundle labels for every type/field here (deterministic).
  Wire `detailTemplates` → `jmix:mainResource` emission.
- **Extraction (`extract_content.py`, `semantic_extract.py`, `vision_extract.py`).** Replace
  the skeleton-freeze + generic body-lift with an **archetype mapper**: per archetype, pull
  the DOM into named fields (`lift_title`→title, hero image→weakref, CTA `<a>`→linkType),
  repeating children→typed child payloads. Images and links leave richtext entirely. Keep a
  `skeletonOrig` **only** as an advisory provenance field, never as the render source.
- **Load (`load_content.py`).** Mostly ready — it already creates childType nodes, weakref
  images, area chrome. Remove the `contribBody*`/`contribImage*` dynamic-slot path; add the
  drop-list (consent/analytics never created).
- **Navigation (`step_nav`).** Promote to primary: emit only the tree-driven
  `ns:mainNavigation`; delete nav-as-skeleton.
- **Theme.** Add a step: tokenize imported CSS (reuse the css-theming reference) into a site
  theme so semantic components render styled.

---

## 6. Gates: from fidelity-pass to authoring-pass

Flip which gates are **blocking**. Fidelity becomes an advisory diff for the human eye;
authoring quality becomes the pass criteria.

**New blocking gates (author `probes/authoring_*`):**

- **archetype-coverage** — every region resolved to a library archetype; `rawHtml` share
  under a hard floor (e.g. ≤5%), each remaining rawHtml block reported for review.
- **semantic-fields** — zero `body2…bodyN` generic slots; every field is a named archetype
  field and has an EN+FR label + `ui.tooltip` (extends the existing `check-cnd.mjs` +
  `jahia-i18n-check`).
- **editability** — zero `<a href>` and zero `<img>` frozen in any richtext field; every link
  is `j:linkType`; every image is weakref. (Scan the content-load payloads.)
- **structured-content** — detected article/news collections are `jmix:mainResource` in a
  contentFolder with a listing + detail template (not page skeletons).
- **navigation** — nav reads the `jnt:page` tree; zero hardcoded nav links.
- **chrome-drop** — no consent/analytics/tracking node exists in the output.

**Demoted to advisory (report, don't block):**
`compose_probe`, `reconstruct_probe`, `groundtruth_probe` — keep producing their diff PNGs /
review HTML so a human can see drift, but a pixel delta no longer fails a run. (Retain a
`faithful-clone` mode for anyone who genuinely wants byte reproduction.)

---

## 7. Phasing

- **P0 — fence the current behavior.** Tag today's pipeline `faithful-clone` mode behind a
  flag; it still works for pure-reproduction use. No regression to it.
- **P1 — archetype library + semantic manifest.** Define the ~12–20 archetype CND templates
  (borrow directly from `mcpShowcase`). Rewrite `segment2manifest` to map→archetype and emit
  labels. Ship `authoring_*` gates as *warn* first.
- **P2 — semantic extractor.** Archetype DOM→field mapper; images/links out of richtext; real
  child nodes. Flip `semantic-fields` + `editability` gates to blocking.
- **P3 — structured content + nav + chrome-drop.** mainResource wiring, tree-driven nav only,
  consent/analytics drop-list. Flip those gates to blocking.
- **P4 — theme import + gate flip.** Tokenize CSS to theme; demote fidelity gates to advisory;
  authoring gates become the run's pass criteria.
- **P5 — proof.** Re-run SingPost end-to-end; verify in Jahia against this contract, opening
  the editor (not just the rendered page).

---

## 8. Risks / open questions

- **Archetype miss rate.** Real sites have long tails. The `rawHtml` floor must be honest —
  a page that's 40% rawHtml is a failed migration, and the gate must say so (no silent
  truncation; this is the "no proxy gates" lesson).
- **Vision vs deterministic archetype classification.** Vision names regions well but
  variably; the archetype vocabulary must be closed and adjudication must snap to it.
- **Theme fidelity.** Accepting pixel drift is the point, but a broken theme import looks
  worse than a frozen skeleton. The advisory fidelity diff is how the human judges "close
  enough."
- **Effort.** This is a doctrine change touching manifest, extractor, loader, nav, and the
  entire gate suite — weeks, not a patch. P1–P2 give the biggest usability jump.

---

## 9. Recommendation

Do **not** keep pushing fidelity-first runs to green — a greener SingPost is a greener
version of the wrong thing. Build P1 + P2 (archetype library + semantic extractor + the two
authoring gates) and prototype on 1–2 SingPost pages so the authoring difference is visible
in the Jahia editor. `mcpShowcase` is the target; the migration should converge on it.
