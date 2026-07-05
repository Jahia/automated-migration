# LIBRARY-SPEC — the base component library (P6, Pillar 1)

**Status:** P6 step-1 deliverable (spec only — no code, no CND, no views yet; those
are P6.1). Source of truth for the plan is `orchestration/MODULARITY-PLAN.md`.

This spec distills the target granularity from **`github.com/Jahia/jahiacom-v3`**
(studied end-to-end: the 4 CND files, `src/server/components/**`, `src/server/views/**`,
`src/server/templates/pages/*.jsx`) and transposes it onto **our stack** (React 19,
`@jahia/javascript-modules-library`, verified against the deployed reference modules
`lesalondelaphoto` / `supercar-garage` / `sial-paris` and `.agents/context/javascript-modules-library-api.md`).

The goal (Julian, 2026-07-04): stop shipping "one big component for the whole page with
as many properties as needed." Ship instead a small palette of **typed atoms → composable
containers → per-page-type zones** so the contributor composes their own page.

---

## 0. What jahiacom-v3 is, and what we take / leave

jahiacom-v3 is a **hand-authored** marketing module. It has **no pixel target**, so it
has no fidelity↔composability tension (MODULARITY-PLAN §3). We take its **taxonomy and
composition mechanics**; we do NOT copy two of its habits:

- **Take:** the atom/section split; category mixins for palette grouping; style mixins as
  choicelist axes; `j:linkType` link pattern; `weakreference picker[type='image']` images;
  fixed-slot `+ name (Type)` vs open `+ * (Type)` child idioms; per-page-type templates
  with per-zone `Area` whitelists.
- **Leave (jahiacom-v3 anti-habits):**
  1. Its sections are mostly **flat "God objects"** — `icon1..icon14`, `title1..16`,
     `content1..N` numbered scalar props (`iconsAnimSection`, `pillarSection`,
     `dropdownMenuNav`, `ourTeamSection`…). That is the SAME anti-pattern our discoverasr
     model has (bodyN). We do NOT reproduce it; repeated units become **child nodes**.
  2. It uses **plain `string i18n`** for titles and bodies (only one richtext field in the
     whole repo: `iconWithText.label`). Our migration rules require `mix:title` as a
     supertype (CLAUDE.md rule 10) and `richtext` for body fields (migration.md rule 3),
     because migrated content contains authored HTML that editors must reformat.

Two jahiacom-v3 internal inconsistencies noted so we don't inherit them: (a)
`cardsCustomerCase` CND declares `+ * (cardJahiaLarge)` but its view hardcodes `large1..4`;
(b) `ButtonDefault` reads `getNodeProps(...,["linkType"])` while the CND prop is `j:linkType`.
Our views read the CND names exactly.

---

## 1. Target taxonomy

Three tiers + two mixin families. Namespace-agnostic: `ns` = per-project content prefix
(e.g. `asr`), `nsmix` = per-project mixin prefix (e.g. `asrmix`). The base library is a
project-agnostic template stamped into each `ns`/`nsmix` at scaffold time.

### 1.1 Category mixins (palette membership) — empty markers

Exactly the jahiacom-v3 pattern (`jahiacomv3mix:jahiacomv3Components` / `…Section`).
These already exist in every migrated module as `nsmix:component` / `nsmix:pageComponent`
(verified: `lspmix:component`, `asrmix:component`). Keep two, add the section marker:

```
[nsmix:component]      > jmix:droppableContent, jmix:accessControllableContent mixin   // atoms
[nsmix:pageComponent]  > nsmix:component mixin                                          // top-level, page-droppable
[nsmix:section]        > nsmix:pageComponent mixin                                      // section-level palette group
```

- Atoms extend `nsmix:component`.
- Containers/sections extend `nsmix:section`.
- `allowedNodeTypes` on an `<Area>` narrows the drop set (see §3); the mixin is what makes
  a type appear in the palette at all.

### 1.2 Style / category-property mixins (reusable property groups)

jahiacom-v3's style axes are all `choicelist[resourceBundle]`. We adopt the same, plus the
two shared field-group mixins already proven in `lesalondelaphoto` (`lspmix:cta`,
`lspmix:media`). Each ships a `ui.tooltip` companion key (CLAUDE.md rule 18).

| Mixin | Properties | Role |
|---|---|---|
| `nsmix:cta` | `ctaLabel (string) i18n`; `j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no` | one contributor link + label (proven: `lspmix:cta`) |
| `nsmix:media` | `image (weakreference, picker[type='image']) < jmix:image`; `imageAltText (string) i18n` | one DAM image + alt (proven: `lspmix:media`) |
| `nsmix:theme` | `theme (string, choicelist[resourceBundle]) < 'light','dark','brand'` | color theme axis (jahiacom-v3 `theme`) |
| `nsmix:background` | `bgColor (string, choicelist[resourceBundle]) < 'bg-white','bg-grey','bg-brand'` | section background (jahiacom-v3 `backgroundColorSection`) |
| `nsmix:spacing` | `spacing (string, choicelist[resourceBundle]) < 'none','sm','md','lg'` | vertical rhythm |
| `nsmix:cornerCut` | `cornerCut (string, choicelist[resourceBundle]) < 'none','cut-topleft','cut-botright'` | jahiacom-v3 `cornerCut` |
| `nsmix:badge` | `badgeLabel (string) i18n`; `badgeStyle (string, choicelist[resourceBundle])` | tag/badge on cards |
| `nsmix:seo` | `metaTitle (string) i18n`; `metaDescription (string, textarea) i18n` | per-CLAUDE.md rule 17 |

Site-level re-theming stays the proven `lspmix:siteTheme` (`:root` token overrides on the
site node) — how a promoted component is "skinned by source tokens" per-site (§5).

### 1.3 Atoms (leaf types — small, single-purpose, typed props)

All extend `> jnt:content, nsmix:component` (+ optional style mixin). Titles via `mix:title`
supertype (never a `title` prop, never `jcr:title` in CND — CLAUDE.md rules 10/kb). Bodies
are `richtext`. Links via `j:linkType`. Images via `weakreference picker[type='image']`.

| Atom | CND (props as written) | jahiacom-v3 origin |
|---|---|---|
| `ns:button` (CTA) | `> jnt:content, nsmix:component, nsmix:cta, nsmix:theme` — inherits `ctaLabel`+`j:linkType`; adds `- isSmall (boolean) = false`, `- mainCTA (boolean) = false` | `buttonItem` |
| `ns:chevronLink` | `> jnt:content, nsmix:component, nsmix:cta` (icon-arrow link) | `chevronButton` |
| `ns:heading` | `> jnt:content, mix:title, nsmix:component` — adds `- subtitle (string) i18n`, `- level (string, choicelist) < 'h2','h3','h4'` | `titleSection` |
| `ns:richText` | `> jnt:content, nsmix:component` — `- body (string, richtext) i18n` | (our addition; migration.md rule 3) |
| `ns:image` | `> jnt:content, nsmix:component, nsmix:media, nsmix:cta` — image+alt (media) + optional link (cta) | `imageItem` |
| `ns:tag` / `ns:badge` | `> jnt:content, nsmix:component, nsmix:badge` — `- tagImg (weakreference, picker[type='image']) < jmix:image`, `- tagImgAlt (string) hidden` | `tagItem` |
| `ns:card` | `> jnt:content, mix:title, nsmix:component, nsmix:media, nsmix:cornerCut, nsmix:theme` — `- body (string, richtext) i18n`; `+ tag (ns:tag)`; `+ button (ns:button)` | `cardJahiaLarge` / `littleCard` |
| `ns:logo` | `> jnt:content, nsmix:component, nsmix:media, nsmix:cta` — a single logo image + link (the discoverasr brand-logo atom, see DECOMP-PROTOTYPE.md) | (derived) |
| `ns:divider` | `> jnt:content, nsmix:component` — `- style (string, choicelist) < 'line','space'` | (our addition) |
| `ns:iconWithText` | `> jnt:content, nsmix:component` — `- icon (weakreference, picker[type='image']) < jmix:image`; `- label (string, richtext) i18n` | `iconWithText` |
| `ns:faqItem` | `> jnt:content, mix:title, nsmix:component` — `- answer (string, richtext) i18n` | `faqItem` |

**Card variants** are style-mixin choices (`nsmix:theme`, `nsmix:cornerCut`,
`widthCard`-style width) on ONE `ns:card` type, NOT separate hash-suffixed types — this is
how granularity generalizes (MODULARITY-PLAN §Pillar1) and avoids the type explosion
(migration.md rule 21: no `ctf:callToActionCard9pqm4` names).

### 1.4 Containers (composable — repeated typed children)

All extend `> jnt:content, nsmix:section` and declare child nodes. **The composable ones use
`+ * (childType)`** (open repeater; editor adds N). Fixed layout uses `+ name (Type)`. We do
**NOT** use `jmix:list` on containers (migration.md rule 11; jahia.md rule 12) — explicit
child declarations only.

| Container | Child declaration | Editor action | jahiacom-v3 origin |
|---|---|---|---|
| `ns:section` | `+ * (nsmix:component)` (open palette of atoms) | add/reorder/remove any atom | `sectionCustom` (open `<Area>`) |
| `ns:gridRow` | `- columns (long) = 3 < 1,2,3,4,6,12`; `+ * (nsmix:component)` (or per-column Areas, proven pattern) | N-col grid of atoms | `lsp:gridRow` (deployed) |
| `ns:cardGrid` | `+ heading (ns:heading)`; `+ * (ns:card)` | grid of cards | `cardsCustomerCase`, `fourArticlesRow` |
| `ns:logoWall` | `+ master (ns:logo)`; `+ * (ns:logo)` | wall of logos | `logosLineSection` |
| `ns:carousel` | `+ * (ns:card)` (or `nsmix:component`) | slides | (news-carousel target) |
| `ns:tabs` | `+ * (ns:tab)` where `ns:tab > mix:title` + `+ * (nsmix:component)` | tabs each holding atoms | `tabs`/`popularDestinationsTabs` target |
| `ns:accordion` | `+ * (ns:faqItem)` | Q/A rows | `faqSection` |

`ns:jcrQuery` + `ns:gridRow` ship in EVERY module (CLAUDE.md rule 16 / migration.md rule 12)
— already present as `asr:jcrQuery`/`asr:gridRow`, `lsp:jcrQuery`/`lsp:gridRow`.

### 1.5 The `rawHtml` skeleton fallback (the shrinking safety net)

`ns:rawHtml` stays (verbatim markup for the tail no library type reproduces faithfully) —
but P6 flips its role from **norm** to **exception**. Every use is a logged "library gap"
that feeds §1.3/§1.4 growth (MODULARITY-PLAN Pillar 2/5). The composability probe counts it
(`composability.py`).

---

## 2. Composition mechanism — jahiacom-v3 → our stack

jahiacom-v3 hand-rolls two helper components; **our stack ships them built-in**, so the
migrator should NOT re-implement them. Signature deltas (verified against the API doc +
deployed modules):

| Concern | jahiacom-v3 (older API) | OUR stack (`@jahia/javascript-modules-library`) |
|---|---|---|
| register | `C.jahiaComponent = defineJahiaComponent({nodeType, componentType, name?})` | `jahiaComponent({componentType, nodeType, name?, displayName?}, (props, ctx) => …)` — one call, props is a `getNodeProps` Proxy |
| context | `useServerContext() → {currentNode, currentResource, renderContext}` | `useServerContext() → {renderContext, currentResource, currentNode, mainNode, jcrSession, bundleKey}` |
| render node | `<Render node={n} />` | `<Render node view? path? content? />` (same; `content=` for virtual nodes) |
| named child | hand-rolled `RenderChildComponent view="x"` (Render-or-AddContentButtons) | **built-in** `<RenderChild name="x" view? readOnly? />` |
| wildcard children | hand-rolled `RenderChildrenComponent nodeTypes={[…]}` (map Render + AddContentButtons) | **built-in** `<RenderChildren filter? pagination? />` — `filter="ns:card"` or a predicate |
| add affordance | manual `<AddContentButtons nodeTypes childName="*" />` | auto-injected by `RenderChild`/`RenderChildren` in edit mode; `<AddContentButtons name? nodeType? parent? />` only for custom layouts |
| zone | `<Area name allowedTypes={[…]} numberOfItems={N} />` | `<Area name nodeType? areaType? />` + **`allowedNodeTypes={[…]}`** (deployed prop name; see §3) |
| image weakref → url | `buildUrl({path: node.getPath()}, renderContext, currentResource)` | `buildNodeUrl(node, options?)` — weakref prop IS a node; call `buildNodeUrl(prop)` |
| link | `buildUrl({path: linkTypeValue, context}, renderContext)` | `j:linkType` resolved by Jahia's link mixins; view reads `j:linknode`/`j:url` injected at runtime |
| module asset url | `renderContext.getURLGenerator().getCurrentModule()` + string | `buildModuleFileUrl("css/x.css")` (wrap ALWAYS — bare strings 404) |

**Composable container view, our-stack canonical form** (transposing jahiacom-v3's
`FaqSectionDefault` / `LogosLineSection`; grounded in deployed `lsp:gridRow`):

```tsx
jahiaComponent(
  { componentType: "view", nodeType: "ns:cardGrid", displayName: "Card Grid" },
  (props, { currentNode }) => (
    <section className={styles.grid}>
      <RenderChild name="heading" />                {/* fixed slot */}
      <RenderChildren filter="ns:card" />           {/* open repeater — add/reorder/remove */}
    </section>
  ),
);
```

`RenderChildren` renders every matching child through the Jahia pipeline AND injects the
"Add Content" button per allowed type in edit mode — this is exactly what makes the block
clickable/editable in Page Builder (contribution rule 28, gate G6b). LIVE keeps byte-exact
output; EDIT interleaves `<Render>` per item.

---

## 3. Zones / page templates

Per-page-type template bound to `jnt:page` with a `name`. Verified deployed form
(`lesalondelaphoto/src/templates/Page/home.server.tsx`): the zone whitelist prop is
**`allowedNodeTypes`** (a const array), not jahiacom-v3's `allowedTypes`.

```tsx
const HERO_TYPES = ["ns:heroCarousel", "ns:heroBanner"];        // restricted zone
const OPEN_PALETTE = ["ns:section", "ns:gridRow", "ns:cardGrid",
  "ns:logoWall", "ns:carousel", "ns:tabs", "ns:accordion", "ns:jcrQuery", "ns:richText"];

jahiaComponent(
  { componentType: "template", nodeType: "jnt:page", name: "home", displayName: "Home" },
  ({ "jcr:title": title }) => (
    <Layout title={title || ""}>
      <Area name="hero" allowedNodeTypes={HERO_TYPES} />
      <Area name="main" allowedNodeTypes={OPEN_PALETTE} />
    </Layout>
  ),
);
```

- **"Zone size" = the granularity of these Areas** (MODULARITY-PLAN Pillar 3). `main` is a
  vertical stack of sections; each section then hosts its own inner `<Area>`/`RenderChildren`
  of atoms. jahiacom-v3 goes one-type-per-Area (`numberOfItems={1}`); we go **one open
  composition Area** (the deployed `lesalondelaphoto` pattern) so contributors freely
  compose — that IS the difference Julian is asking for.
- The **page-type SET** is derived automatically by clustering pages on structural signature
  (P6.3) — same structure → same template. `template-cluster.sh` / `semantic-templates.json`
  already exist to seed this.
- `AbsoluteArea name parent={site.getNode("home")} readOnly="children"` for header/footer
  (jahia.md rule 15; deployed pattern).

---

## 4. Repo rules the library must honour (checklist)

From CLAUDE.md / `.claude/rules/*` — these are non-negotiable and the P6.1 generator must
encode them:

1. `j:linkType (string, choicelist[linkTypeInitializer])` for every contributor link; NEVER
   declare `j:url`/`j:linknode` in the CND (jcr.md; migration.md rule 9 superseded).
2. Images = `weakreference, picker[type='image'] < jmix:image`; never a URL string
   (migration.md rule 15). DAM weakref, verbatim-default contract (migration.md rule 26).
3. `mix:title` supertype for titles; never `jcr:title` / a bespoke `title` prop in CND.
4. `richtext` for bodies (migration.md rule 3); no `string` for HTML-bearing fields.
5. Every field key has a `ui.tooltip` companion in the resource bundle (CLAUDE.md rule 18).
6. EN + FR at minimum; keep `en.json`/`fr.json` in sync (CLAUDE.md rules 4/12).
7. Ship `ns:jcrQuery` + `ns:gridRow` per module (CLAUDE.md rule 16).
8. Extract shared property groups into `nsmix:*` mixins before the 2nd type (CLAUDE.md rule
   17) — this spec does: `nsmix:cta`, `nsmix:media`, `nsmix:badge`, `nsmix:seo`, style mixins.
9. Never `jmix:list` on containers; explicit `+ *`/`+ name` children (migration.md rule 11).
10. Never `jmix:droppableContent` directly — always via `nsmix:component` (jahia.md rule 10).
11. `jmix:cache` does not exist in 8.2 (jahia.md rule 12).
12. Every component passes WCAG 2.1 AA (CLAUDE.md rule 19).

---

## 5. What differs from a hand-authored library: fidelity

jahiacom-v3 renders whatever its CSS says. A **migration** must render byte-identical to the
captured source (ground-truth gate ≥99%). So the base library carries two migration-only
mechanisms absent from jahiacom-v3:

1. **Parametric CSS skinned by source tokens.** Each library component ships CSS driven by
   `:root` tokens (via `lspmix:siteTheme` on the site node). At migration time the extractor
   maps the source's per-component classes (for the brand-logo grid: `.asr-section-brands-logo`,
   `.logos-wrapper`, `.brand-logo` — confirmed present in the discoverasr source CSS) onto the
   library component's token set, so a promoted `ns:logoWall` reproduces the source layout
   without a frozen skeleton. Fidelity is verified on the COMPOSED render, not asserted.

2. **Skeleton-fallback as a fidelity floor.** Decomposition (P6.2) promotes a DOM subtree to a
   library type ONLY if the composed render is pixel-verified against source; otherwise it
   falls back to `ns:rawHtml` verbatim (fidelity before contribution — migration.md rule 23).
   The verbatim-default contract (migration.md rule 26) means an unedited promoted node is
   byte-exact by construction (renders its captured `imageNOrig`/`linkOrig` until an editor
   changes it). This is the fidelity↔composability reconciliation: every node is EITHER a
   pixel-verified typed atom OR a verbatim fallback — never a lossy approximation.

The tension, named: the more aggressively we promote (higher composability), the more we risk
a promotion whose CSS skin doesn't exactly reproduce source (lower fidelity). P6.2 exposes an
**altitude/aggressiveness knob**; the composability probe (this deliverable's sibling) and the
ground-truth gate together bound it. Open question carried to P6.1/P6.2 in the plan.
