# P2.5 — Contribution model

Status: **COMPLETE 2026-07-03 — all four gates green on acquia-drupal** (approved by Julian
same day; pre-registered before implementation, per QUALITY-PLAN discipline — full log in
QUALITY-PLAN §7).

| Gate | Result |
|---|---|
| G1 static contribution | **PASS** — min 89.1 % / avg 98.1 % forms-excluded (floors 60/85); dead props 0, phantom markers 0, empty shells 0 |
| G2 round-trip | **PASS** — 18/18 sentinel edits visible live, all restored (probe polls: publication is async) |
| G3 fidelity | **PASS** — ground truth 18/18 pages = 100 % after G2 mutations (careers 99.93 → 100) |
| G4 editorial | **PASS** — careers = acq:contentGrid + 5 × acq:contentGridItem; card heading+copy editable as item body richtext (span-wrapped headings stay in richtext, strict jcr:title lift = pure-text headings only) |

**Phase C COMPLETE 2026-07-03** — G5a media 97.1 % (floor 90), G5b links 100 % (floor 95),
G2+ 23/23 round-trips (incl. 4 media swaps + j:url sentinel), G3 18/18 ≥99 % with wiring
live, G1 zeros hold. 162 DAM files, 201/207 media units wired, 60/60 link payloads wired
(5 external, 3 internal resolved, 52 honest linkOrig fallbacks). See §8 + QUALITY-PLAN §7.

**P2.5-D (same day):** slot props moved from types to per-node mixins
(`acqmix:contribBody[N]`/`contribImage[N]`/`contribLink` + mix:title, added by the loader)
— the editor form shows EXACTLY the fields each node carries; no more empty unjustified
body2/body3 on leaner nodes. Re-certified: GT 18/18, round-trip 23/23, parity green.

---

## 8. Phase C design (REGISTERED 2026-07-03, before implementation/measurement)

Measured landscape on acquia (post-P2.5 skeletons, outside body richtext):
203 media units (76 standalone `<img>`, 127 `<picture>`, 0 bare-srcset), 119 residue
links (95 internal / 24 external). Card headings wrapped in inline spans were swallowed
by body runs — C1 fixes the lift, not the residue.

### C1 — Title lift generalization
`lift_title` also accepts a heading whose subtree contains EXACTLY ONE non-whitespace
text node (span/strong wrappers stay in the skeleton; the marker replaces the text node).
Round-trip rule unchanged (minimal-escape equality). Card titles then land in jcr:title
and LEAVE the body richtext.

### C2 — Media contract (fidelity-safe by construction)
- Unit = a whole `<picture>` element or a standalone `<img>` in skeleton residue.
- Per payload, up to **6** units wired (`image`..`image6` — weakreference,
  picker[type='image'], < jmix:image); the rest stay verbatim and are COUNTED.
- Per unit, two hidden companions: `imageNOrig` (the unit's exact original markup) and
  `imageNOrigRef` (UUID of the DAM copy of the original primary file).
- The unit's primary file (img@src) is uploaded ONCE per unique asset to
  `/sites/<site>/files` via `media.upload.create/PUT/finalize` (dedupe map committed to
  `orchestration/images/<project>.dam.json`), published, and the weakref defaults to it.
- View render: weakref UUID == origRef -> splice the ORIGINAL markup verbatim
  (default state stays byte-exact — G3 protected by construction). UUID differs
  (editor picked another image) -> original markup with img@src swapped to the chosen
  node URL, `<source>` elements and srcset dropped (the chosen image must win).
  Responsive variants are lost ON EDIT ONLY — accepted editorial trade, recorded.
- Images inside body richtext stay richtext-managed (already editable) — not wired.

### C3 — Link contract
- Unit = residue `<a href>` (href not `#...`); **the FIRST unit per payload** is wired
  (Jahia's j:linkType/j:url/j:linknode are node-level singletons); the rest stay
  verbatim and are counted.
- Markers: href value -> `{{link:href}}`; anchor label -> `{{f:linkLabel}}` only when
  the anchor has exactly one non-ws text node.
- CND: `j:linkType (string, choicelist[linkTypeInitializer])` + `linkLabel` per rule
  14/9 — j:url/j:linknode NEVER declared (mixin-injected; loader does GraphQL addMixins,
  the proven flow).
- Loader: external href -> jmix:externalLink + j:url = original href (default render
  byte-exact). Internal href -> resolve against the migrated page set; resolvable ->
  jmix:internalLink + j:linknode (default render = Jahia page URL — byte-different,
  PIXEL-identical; the correct target on the migrated site). Unresolvable internal
  (page not migrated) -> NOT wired, verbatim, counted.
- View: `{{link:href}}` <- j:url or linknode URL; label substitution as a text field.

### Pre-registered phase-C gates (frozen now)
| Gate | Threshold |
|---|---|
| G5a media | ≥ 90 % of media units wired (unwired = over-cap or malformed, listed by the probe) |
| G5b links | ≥ 95 % of payloads holding ≥1 residue link have their PRIMARY link wired (j:linkType is a node-level singleton — C3; secondary anchors stay verbatim and are counted). Internal: wired when the target page is migrated; probe prints external/resolved/unresolved. *(Amended from "95 % of external links" before any measurement — the original wording contradicted C3's first-unit-per-payload design.)* |
| G2+ | round-trip extended: image weakref swap changes the live `<img>` src; j:url sentinel appears in live href; both restore |
| G3 | unchanged — ground truth 18/18 ≥ 99 % with DEFAULT state (all origRef equalities hold) |
| G1 | unchanged — text coverage floors 60/85, zeros hold |
Trigger: editorial review of the deployed acquia site (screenshots: careers Content Grid,
featureBlock-careers-9, home "Acquia Source" hero) — the migration is NOT usable by CMS
contributors in its current state.

---

## 1. Diagnostic (measured on the committed P2 state, `2bd71cc`)

The P2 gate `semanticLeafShare` (min 69 % / avg 96 %) measured **structural coverage**
(content leaves living under a promoted typed node). It does NOT measure contribution.
The honest contribution numbers on acquia-drupal:

| Metric | Value |
|---|---|
| Visible main-region text living in an **editable, wired** property | **1.8 %** (1 735 / 95 292 chars) |
| `title` props wired to the render (substituted) | 48 / 60 |
| `text` props wired to the render | **3 / 62** → 59 DEAD props (editing changes nothing) |
| Promoted instances with ZERO wired fields ("empty shells") | 19 / 67 |
| Images referenced but baked in skeleton (no editable prop) | 151 |
| Links baked (no j:linkType) | 171 |

### Three root causes (all in the LOAD path — extraction/typing are fine)

1. **Group-altitude aggregation** — `extract_content.emit_promoted` lifts only
   `title` + `text`, where `text` = whitespace-normalized `fullText` of the WHOLE
   top group (all cards concatenated, `img` alt placeholders inlined as "Image").
   → the careers Content Grid body = one blob of 5 cards.
2. **String-unique-match substitution** — `make_skeleton` searches the serialized
   HTML for the normalized field value. An aggregated/normalized string almost never
   occurs verbatim → 59/62 `text` missed → the prop LOADS but is **dead** (skeleton
   keeps the original markup inline; edits never reflow). Worst case: home
   "Acquia Source" hero — title AND text missed; "Your Command Center" exists only
   inside the hidden skeleton; the editor form shows props that lie.
3. **Items never become child nodes** — the manifest already defines
   `childType` for 17/17 containers (deployed CND: `acq:contentGridItem` with
   body/image, `acq:pressReleaseCardsItem` with title/body/image/j:linkType…)
   and the vision segmentation already provides **135 item boundaries** across 33
   container segments — but the loader collapses everything into one monolith node.

**Metric lesson (recorded, not retroactive):** `semanticLeafShare` stays as the
structural dial; a NEW metric is added for what editors actually experience.

---

## 2. New pre-registered metric

**Contributable-text coverage** = share of visible text chars in `<main>` that live in
an editable (i18n) JCR property **whose modification round-trips to the live render**
(mutation → cache flush → re-render → new value visible, old value gone).

Three companion ZEROs (binary, per site):
- **0 dead props** — every property shown in Content Editor affects the render
  (a field that cannot be structurally placed is NOT loaded, and is counted).
- **0 empty shells** — a promoted instance with no wired field must not exist;
  it is either decomposed further or loaded as an honest `rawHtml` block.
- **0 phantom content** — no visible text that lives in NO editable property while a
  sibling property pretends to hold it.

## 3. Pre-registered gates (acquia-drupal first; thresholds frozen now)

| Gate | Threshold | Judge |
|---|---|---|
| G1 contribution (static) | coverage ≥ 60 % min/page, ≥ 85 % avg; dead props = 0; empty shells = 0 | `probes/contribution.py` on content-load + deployed props |

**Metric refinement (registered 2026-07-03, BEFORE the probe exists, based on spike
feasibility data — not on a gate run):** text inside `<form>` subtrees is excluded
from the G1 denominator — form widgets/labels are script-driven webform content, not
contributor richtext (measured: 83 % of the contact page's main group text lives in
its Drupal webform). The probe MUST print both numbers (raw and forms-excluded);
the gate judges forms-excluded. No other exclusions.
| G2 round-trip (dynamic) | sample ≥ 3 props/page × 6 pages: sentinel edit visible in live; after revert, ground truth re-PASS 18/18 ≥ 99 % | `probes/roundtrip.sh` |
| G3 fidelity (unchanged invariant) | ground truth 18/18 pages ≥ 99 % | existing `probes/groundtruth.sh` |
| G4 editorial | careers = 1 Content Grid + 5 item children, each with editable title/body/image; home hero title+body editable and wired | manual/cockpit review |

Fidelity remains the hard invariant: any mechanism change that drops G3 is reverted,
never accommodated by threshold changes.

## 4. Mechanism — four workstreams

### A. Structural (DOM-level) substitution — kills dead props by construction
Replace `make_skeleton` string search: fields are extracted WITH a reference to their
source element; the `{{f:name}}` marker replaces that element's **content in the tree**,
then the skeleton is serialized. A field with no placeable element is dropped from the
load (never loaded dead) and counted. Expected misses ≈ 0.

### B. Per-item decomposition — parent + child nodes at vision boundaries
`emit_promoted` splits a promoted group into:
- parent node: skeleton = group markup with each item subtree replaced by `{{child:i}}`
  (inter-child whitespace preserved byte-exact — fidelity by construction);
- one child node per vision item boundary (heuristic repeat-detection as fallback),
  typed by the manifest's existing `childType`, fields extracted at ITEM scope:
  `title` = item heading, `body` = **richtext innerHTML** of the item's text container
  (inline markup preserved — no more "Image" placeholder soup; migration rule 3).
SkeletonView renders `{{child:i}}` markers by rendering the child nodes in document
order. **Spike #1 (day one): validate in-view child-node rendering + byte-identical
recomposition on the careers Content Grid before generalizing.**

### C. Media & links — the CMS-correct references
- Images → DAM: upload mirror images to `/sites/<site>/files`, filename→UUID map,
  `image` (weakreference) prop per item (rule 15), marker in skeleton, view renders
  the same `<img>` classes/alt from the node. Raises coverage + fixes 151 baked images.
- CTA links → `j:linkType` + `jmix:externalLink`/`internalLink` via GraphQL
  `addMixins` (mechanism already proven on the deployed module).

### D. Probes & plan integration
- `orchestration/probes/contribution.py` (G1) — deterministic, reads content-load +
  GraphQL prop introspection.
- `orchestration/probes/roundtrip.sh` (G2) — sentinel mutation, output-cache flush,
  live assert, revert, ground-truth re-run.
- `gen_plan.py`: add both probes to the deterministic plan; cockpit KPI panel follows in P3.

## 5. Sequencing

1. **A + B + D** on acquia (text is the bulk of contribution value) → G1, G3, G4.
2. **C** (images/links) → coverage rises, G1 re-measured.
3. **G2** last (needs stable props).
4. **P3 (3 sites) starts only after P2.5 is green** — we scale a contributable
   architecture, not the monolith. P3/P4 pre-registered goals unchanged, with G1/G2
   added to their gate set.

## 6. Named risks

- **Fidelity regression** via parent/child recomposition → byte-identical serialization
  is a construction requirement, G3 re-run at every iteration.
- **In-view child rendering** in JS-module server views — pattern must be validated by
  Spike #1 before mass generation.
- **Coverage ceiling**: webforms, animated counters, script-driven widgets will stay
  passthrough → floors are 60/85, not 100; exclusions must be visible in the probe
  output, never silent.
- **richtext power**: editors can break item markup — accepted CMS contract.

## 7. Files touched (expected)

`orchestration/lib/semantic_extract.py` (element-ref field extraction),
`orchestration/lib/extract_content.py` (emit_promoted rewrite: DOM skeleton,
child emission, richtext), `orchestration/lib/load_content.py` (child-node creation,
richtext/weakref props, addMixins for links), `orchestration/lib/segment2manifest.py`
(item-scope child fields), `orchestration/templates/fidelity-shell/SkeletonView.tsx.template`
(+ child rendering), new `orchestration/lib/dam_import.py`, new probes (D),
`orchestration/lib/gen_plan.py`, QUALITY-PLAN §7 log entries at every milestone.
