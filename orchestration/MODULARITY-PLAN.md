# MODULARITY-PLAN — P6: modular, contributable component models

**Status:** proposed & approved (Julian, 2026-07-04). Restart-from-0 authorized:
discoverasr Jahia site DELETED (provisioning `deleteSite`), old module to be
undeployed + `asr` namespace purged at P6 redeploy via `validate-module` (rule 13).
Upstream capture (mirror / crawl / semantic) PRESERVED and reused — P6 reworks the
**pre-Jahia recomposition**, not the source capture.

---

## 1. The problem (Julian, 2026-07-04)

> « Un gros composant pour la page entière, avec autant de propriétés que nécessaire.
> Ce n'est absolument pas modulaire ni contribuable. Le contributeur doit pouvoir
> composer sa propre page. »

Measured on discoverasr: **71 CND types, 48 skeleton/`bodyN` lines, ~2560 `rawHtml`
passthrough nodes**. The pipeline **captures-and-freezes**: vision segmentation groups the
DOM into sections, then each section becomes a `skeleton` (frozen markup) + lifted
`body1..bodyN`/media/link fields. Structure is baked into markup; a contributor edits the
*text* inside a frozen section but cannot **compose** a page (add / reorder / remove
blocks). Container children are `asrmix:component` skeleton blobs, not a palette of
reusable typed atoms.

This is the P6 / Q2.2 blind spot already flagged: **G1 measures editable TEXT, not
editable STRUCTURE — the other half of the CMS value, never started.**

## 2. The target (reference: github.com/Jahia/jahiacom-v3)

Right granularity, **recognize-and-compose**:

- **Atoms** (`jahiacomv3mix:jahiacomv3Components`): `buttonItem`, `tagItem`,
  `titleSection`, `cardJahiaLarge`, `littleCard`, `chevronButton` … small, single-purpose,
  typed props (title, text, `weakreference` image, `j:linkType`).
- **Sections** (`jahiacomv3mix:jahiacomv3Section`) = **containers of typed children**:
  `cardsCustomerCase` is `+ * (jahiacomv3:cardJahiaLarge)` (editor adds N real cards);
  `+ button (jahiacomv3:buttonItem)` (named single child).
- **Category mixins** (`…Section` / `…Components`) group types in the editor palette;
  **style mixins** (`theme`, `cornerCut`, `btnStyle`, `backgroundColorSection`) = reusable
  property groups.
- **Zones** = per-page-type templates (`PageHome`, `PagePillar`, `PageProduct`…) declaring
  `<Area name allowedTypes numberOfItems>`; intra-container composition via
  `RenderChildrenComponent` (`<Render node>` + `<AddContentButtons>` — the editor gets an
  "add" button per allowed type in each zone).

## 3. The core tension (must be named)

**Fidelity (byte-exact skeleton) ⟷ Composability (typed atoms re-rendered from
props/children).** jahiacom-v3 is hand-authored with no pixel target, so it has no tension.
A *migration* does. The whole plan is to move as much structure as possible from **frozen
skeleton** to **composable library components WITHOUT losing fidelity** — skeleton becoming
the shrinking safety-net for the tail the library cannot yet reproduce, not the norm.
Never violate the fidelity doctrine (never generate content): P6 **RE-STRUCTURES captured
content into typed nodes; it never invents content.**

## 4. The plan — 5 pillars

### Pillar 1 — a shared, versioned COMPONENT LIBRARY (the palette)
A project-agnostic base library modeled on jahiacom-v3's taxonomy:
- Atoms: `cta/button`, `heading/title`, `richText`, `image`, `tag/badge`, `card`
  (variants), `divider`.
- Containers (all `+ * (nsmix:component)` composable): `section`, `grid`/`row` (N cols),
  `carousel`, `tabs`, `accordion`.
- Style mixins: `theme`, `background`, `spacing`, `cornerCut`.
Each ships **parametric CSS skinned by tokens extracted from the source**, so a promoted
component reproduces the source pattern. **This is how granularity generalizes**: not 71
bespoke types per project, but ~15–25 shared types + a per-project skin.

### Pillar 2 — recursive structural decomposition (lower the altitude) — PRE-JAHIA
Change the pre-Jahia `group`/recompose stage from "section → skeleton" to a recursive
descent that **maps DOM subtrees onto the library**: section → rows/columns → cards →
atoms. At each node, try to map to a library component (repeated card grid → `grid` of
`card`; heading+text+button → `section` with `heading`+`richText`+`cta`; `<ul>` of links →
`linkList`). Where the mapping **reproduces the source (pixel-verified)** → **promote** to
the typed composable component (real child nodes; editor free to add/reorder/remove). Where
no mapping is faithful → **skeleton fallback** (fidelity preserved), logged as a "library
gap" that feeds library growth. This is **recognize-and-map** replacing **capture-and-freeze**.
Library membership bounds the type explosion.

### Pillar 3 — zone/area model (page templates define zones)
Per-page-type templates declaring `<Area name allowedTypes numberOfItems>`. **"Zone size" =
the granularity of those areas**: `main` = vertical stack of sections; each section = 1–N
inner areas accepting atoms. The page-type set is **derived automatically** from clustering
pages by structural signature (same structure → same template).

### Pillar 4 — a COMPOSABILITY gate (measurable, enforced)
New gate alongside G1/G6 that measures modularity, not just text:
- ratio of composable-typed structure vs frozen skeleton (target: skeleton a minority;
  **0 full-page monoliths**);
- every container is `+ *` with a sensible `allowedTypes` palette;
- **no type carries more than K lifted fields** (the "one component for the whole page with
  as many props as needed" anti-pattern → HARD FAIL; beyond K it must decompose into
  children);
- Page Builder composability smoke: add a new atom to a section area, reorder, remove — per
  template.
This gate is what **prevents regression to page-sized components across ALL projects,
generically.**

### Pillar 5 — fidelity reconciliation (keep both)
Library CSS is skinned from source tokens → promoted components reproduce source pixels;
the ground-truth gate runs on the composed render. Skeleton fallback remains the safety-net
for the shrinking tail; each fallback is a logged library gap. (Related: the current
ground-truth ceiling on discoverasr is 1 real structural defect + rule-35 vertical-drift
noise dominated by a constant ~+322px header delta — a clean `header` library component
fixes the height AND enables a shift-tolerant fidelity check.)

## 5. Phasing

- **P6.1** — Build the base library (atoms + containers + style mixins + parametric CSS)
  from jahiacom-v3; ship the composability gate that first **measures current debt**
  (baseline).
- **P6.2** — Recursive decomposition + library mapping in the pre-Jahia `group` stage,
  behind an altitude/aggressiveness knob; promote if pixel-verified, skeleton-fallback
  otherwise; redeploy discoverasr from 0 (undeploy old bundle + purge `asr` namespace via
  `validate-module`, rule 13) and measure composability + fidelity.
- **P6.3** — Page-type templates with zones/`allowedTypes`; per-project page clustering →
  template set.
- **P6.4** — Iterate library coverage until skeleton-fallback < threshold on the reference
  sites; the composability gate becomes hard like G1/G6.

## 5b. Locked decisions (Julian, 2026-07-04)

- **Altitude = FIDELITY-FIRST.** Promote a DOM subtree to a typed composable component ONLY
  when the composed render is pixel-verified against the source mirror; otherwise `rawHtml`
  fallback + log the library gap. Fidelity never regresses; composability rises with library
  coverage.
- **K = 8** (max lifted fields per type before mandatory decomposition). discoverasr's worst
  is 35/34; a rich card (heading+body+image+cta+badge = 5) stays under 8. Calibrate against
  acquia/supercar's richest legit cards before flipping composability.py to a HARD gate.
- **In-stack reference: `lesalondelaphoto` already ships the target model** (`gridRow` +
  `<Area allowedNodeTypes={OPEN_PALETTE}>`). P6.1 builds the base library by generalizing
  THAT working pattern, not by inventing from jahiacom-v3 (whose sections are partly
  God-objects — do not inherit `icon1..14`/`title1..16` or plain-string bodies).
- Baseline composable ratio: discoverasr 0.0% · contentful 31.2% · supercar 53.4% ·
  acquia 57.0% (from `composability.py`).

## 6. Step 1 (done — commits 1639976 / b8d6808 / d6a33b9)

1. Distill jahiacom-v3 end-to-end (CND + views + templates + area/allowedTypes/child-render
   declarations) into a **base-library spec**.
2. Build a **composability-debt instrument** and quantify discoverasr's current model
   (full-page skeletons, composable-vs-skeleton ratio, bespoke type count, max lifted
   fields per type).
3. Prototype recursive decomposition on ONE discoverasr section (brand-logos grid or a card
   grid) → promote to `grid` of `card` atoms; verify fidelity holds AND an editor can
   add/remove a card.
