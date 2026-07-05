# DECOMP-PROTOTYPE — recursive decomposition on one real discoverasr section

**Status:** P6 step-1 deliverable (feasibility proof on paper/data, NOT pipeline code —
that is P6.2). Source of truth: `orchestration/MODULARITY-PLAN.md` (Pillar 2). Companion:
`orchestration/LIBRARY-SPEC.md` (the target types), `orchestration/probes/composability.py`
(the debt this fixes).

Section chosen: **`brands-logo-section`** (the brand-logo wall on the discoverasr home page).
All data below is read from on-disk artifacts only — the Jahia site is deleted:
- markup: `projects/discoverasr/workflow-output/html-fragments/brands-logo-section.html`
- current model: the `brands-logo-section` instance in
  `orchestration/content/discoverasr.content-load.json` (page `en`)
- source CSS classes confirmed present in `projects/discoverasr/static/assets/*.css`.

---

## 1. What the CURRENT model produced (the debt, concretely)

CND (`projects/discoverasr/settings/definitions.cnd`):
```
[asr:brandsLogoSection] > jnt:content, asrmix:component
  - skeleton (string, textarea) hidden
```
Instance in the content-load plan (page `en`), captured as ONE frozen node:
- `skeleton` = 3385 bytes of the whole wall's markup;
- `media` = 16 units (`image`…`image16`) → `{{media:imageN}}` markers in the skeleton;
- `link` = ONE unit (`/en/our-brands`) → the single `{{link:href}}` marker, on the master logo;
- `fields` = **[]** (no text — probe shows `brands-logo-section maxK=17, 0 body*, 16 img, 1 link`).

The source wall has **19 logos**: 1 `<a class="master-logo">` + 18 `<a class="brand-logo">`
(grep-confirmed on the fragment). The skeleton pins **18 hardcoded `href` literals**, exposes
**1 `{{link:href}}` marker** (the master) and **16 `{{media:imageN}}` markers**
(counts verified against the content-load instance).

Two concrete failures a contributor hits:
1. **No structure.** It is one node. A contributor cannot add a new brand, remove a
   defunct brand, or reorder logos. The wall is frozen markup.
2. **Only 1 of 19 links is editable.** The skeleton pins the other 18 anchors' `href` as a
   **hardcoded literal** (`href="https://www.discoverasr.com/en/our-brands"` appears verbatim
   18 times in the skeleton). Editing any of those 18 destinations is impossible. And because
   `media` caps at 16 (contribution rule 26), 3 of the 19 logos have no editable image slot
   at all — they render only from the frozen markup.

This is exactly the "one big component with as many props as needed" anti-pattern
(MODULARITY-PLAN §1): it maximised lifted fields on ONE type instead of lowering the altitude.

---

## 2. The SOURCE markup (abridged — real structure, real classes)

```html
<div class="asr-section-brands-logo">
  <div class="logo-container wrap">
    <div class="master-logo-wrapper">
      <a class="master-logo" href="https://www.discoverasr.com/en/our-brands">
        <picture><img alt="TAL and ASR" class="logo" loading="lazy"
             src="assets/5bfcad52f50ae514.svg" title="TAL and ASR"/></picture>
      </a>
      <div class="line"></div>
    </div>
    <div class="logos-wrapper">
      <a aria-label="Brand Logos" class="brand-logo" href="https://www.discoverasr.com/en/our-brands">
        <picture><img alt="Brand Logos" class="logo" loading="lazy"
             src="assets/f9a5ce225e64d520.svg"/></picture>
      </a>
      <div></div>
      <a aria-label="Brand Logos" class="brand-logo" href="...">...src="assets/0676575423600bfd.svg"...</a>
      <div class="break-mobile"></div>
      <!-- … 15 more identical <a class="brand-logo"> siblings + <div class="break-*"> spacers … -->
    </div>
  </div>
</div>
```
Signature: a wrapper (`.asr-section-brands-logo` → `.logo-container` → `.logos-wrapper`)
containing **1 master logo** + **18 repeated same-signature `<a class="brand-logo">` siblings**,
each = one `<picture><img></picture>` + one `href`. The interleaved empty/`break-*` `<div>`s
are pure responsive-layout spacers (no content) — CSS concern, not nodes.

---

## 3. The recursive descent (recognize-and-map, MODULARITY-PLAN Pillar 2)

At each DOM node, try to map onto a library type (LIBRARY-SPEC §1); recurse; where a repeated
same-signature sibling set of size ≥3 is found, lift the siblings to CHILD NODES
(contribution rule 24), NOT one monolith.

```
.asr-section-brands-logo                         → asr:logoWall            (container, LIBRARY-SPEC §1.4)
  .master-logo-wrapper > a.master-logo           → + master (asr:logo)     (fixed named slot)
  .logos-wrapper                                  → the + * (asr:logo) repeater host
    a.brand-logo  (×18, repeated signature ≥3)   → 18 × asr:logo           (child nodes)
    div, div.break-*                              → dropped as nodes; reproduced by asr:logoWall CSS
```

Recognizer that fires here: **"repeated anchor-wrapping-image siblings under a common
parent"** → `logoWall` of `logo`. The single leading `a.master-logo` differs (own class,
own wrapper) → the named `master` slot. This is a deterministic structural rule (same class,
same child shape, count ≥3), never content generation (fidelity doctrine).

---

## 4. The TARGET node tree (typed atoms + props + children)

```
asr:logoWall  "Brands Logo Section"          [> jnt:content, asrmix:section]
│   (view renders .asr-section-brands-logo > .logo-container.wrap > .logos-wrapper,
│    skinned from source .asr-section-brands-logo / .logos-wrapper / .brand-logo CSS)
│
├── master  = asr:logo                        [+ master (asr:logo) — fixed slot]
│     image      → weakref → DAM copy of 5bfcad52f50ae514.svg   (asrmix:media)
│     imageAltText = "TAL and ASR"
│     j:linkType  = external, j:url = https://www.discoverasr.com/en/our-brands  (asrmix:cta)
│     ariaLabel/variant = "master"            (renders <a class="master-logo">)
│
└── logos   = asr:logo × 18                    [+ * (asr:logo) — OPEN repeater; add/reorder/remove]
      logo-1:  image → f9a5ce225e64d520.svg ; alt="Brand Logos" ; link → /en/our-brands
      logo-2:  image → 0676575423600bfd.svg ; alt="Brand Logos" ; link → /en/our-brands
      logo-3:  image → b264d27786db630e.svg ; …
      …
      logo-18: image → a71750cb424b0ac4.svg ; alt="Brand Logos" ; link → /en/our-brands
```

Each `asr:logo` atom (LIBRARY-SPEC §1.3) = `asrmix:media` (image weakref + alt) +
`asrmix:cta` (label + `j:linkType`). So **all 19 links become editable** (vs 1 today), all 19
images become DAM weakrefs (vs 16 capped + 3 frozen), and the editor can add/remove/reorder
any logo via `<RenderChildren filter="asr:logo" />` (LIBRARY-SPEC §2).

Debt delta for this one section (per `composability.py` accounting):
| | current | after decomposition |
|---|---|---|
| nodes | 1 frozen | 1 container + 19 typed atoms = 20 composable nodes |
| max lifted fields on any node (K) | 17 | ≤3 per `asr:logo` (image, alt, link) — under K=8 |
| full-page monolith? | the 3385B skeleton counts toward frozen | 0 |
| editable links | 1 / 19 | 19 / 19 |
| editable images | 16 / 19 | 19 / 19 |
| editor can add/remove a logo? | no | yes (`+ * (asr:logo)`) |

---

## 5. Recomposition markers & the byte-exact contract

Decomposition self-checks the same way today's skeleton does (contribution rule 23): the
container keeps a skeleton whose child-slot markers place each atom back on the SOURCE
element in the tree, and `recompose(container_skeleton, children)` must equal the original
byte-for-byte or the group falls back to `asr:rawHtml` verbatim (fidelity before contribution).

Container skeleton (schematic — markers replace the lifted subtrees, spacers kept verbatim):
```html
<div class="asr-section-brands-logo"><div class="logo-container wrap">
  <div class="master-logo-wrapper">{{child:master}}<div class="line"></div></div>
  <div class="logos-wrapper">
    {{child:0}}<div></div>{{child:1}}<div></div>{{child:2}}<div class="break-mobile"></div>
    {{child:3}}…{{child:17}}<div></div>
  </div>
</div></div>
```
Each `asr:logo` child carries its own atom-level skeleton so its unedited render is byte-exact:
```html
<a aria-label="Brand Logos" class="brand-logo" href="{{link:href}}">{{media:image}}</a>
```
where `{{media:image}}` defaults to the exact captured `<picture><img …></picture>` (the
verbatim-default contract, rule 26 — `imageOrig`/`imageOrigRef`), and `{{link:href}}` defaults
to the captured `href`. Result: **an unedited decomposed wall is byte-identical to the source**;
every edit reflows into the same markup. This is the standing skeleton machinery
(`semantic_extract.decompose_group` / `recompose_group`) applied ONE LEVEL DEEPER — per
`asr:logo` child, not per whole section.

---

## 6. Fidelity point: does the library CSS reproduce the render?

Yes, by construction, because the promoted `asr:logo` renders through the SAME markup the
skeleton captured (`<a class="brand-logo">` + `<picture><img class="logo">`) and the source
CSS classes it depends on — `.asr-section-brands-logo`, `.logo-container`, `.logos-wrapper`,
`.brand-logo`, `.master-logo`, `.break-mobile` — are all present in the discoverasr source
CSS (grep-confirmed in `static/assets/*.css`) and already imported by the module. The
`asr:logoWall` library component's CSS is skinned from exactly those classes (LIBRARY-SPEC
§5), so the composed render is pixel-identical to the frozen one. The responsive `break-*`
spacers stay in the container skeleton (layout, not content), so the flex-wrap breakpoints
are preserved.

Promotion is gated: P6.2 promotes `asr:logoWall` ONLY if the composed render passes the
ground-truth pixel check vs the source mirror; otherwise it stays `asr:rawHtml` (the current
behaviour) and logs a library gap. Fidelity is never traded away — composability is added
on top of a byte-exact floor.

---

## 7. Open items this prototype surfaces (carried to P6.1/P6.2)

1. **Repeated-sibling threshold.** Here 18 ≥ 3 → clearly items. But rule 24 warns repeated
   `<p>`/`<h*>`/`<ul>` are a text RUN, not items. The recognizer must key on
   "element wraps media/link" (structural), not just "sibling repeats" — else a paragraph run
   becomes N empty nodes (the Next.js failure). `brand-logo` passes (wraps an `<img>`+`href`).
2. **Master-vs-item disambiguation.** The leading `a.master-logo` differs by class — a fixed
   `master` slot. Generalise: siblings that share a signature → `+ *`; the odd-one-out with
   its own wrapper/class → a named slot. Needs a per-signature clustering step.
3. **The K cursor.** With decomposition, `asr:logo` carries ≤3 fields — well under K=8. But
   `cardGrid`/`section` cards may carry heading+body+image+cta+badge = 5. K=8 leaves headroom;
   confirm against acquia/supercar where richer cards exist.
4. **The fidelity↔composability altitude knob (the main P6.2 arbitrage).** How aggressively
   to promote before a skin mismatch risks fidelity. This section is a "safe" promotion
   (verbatim media/link defaults, source CSS reused). Harder cases (bespoke section layouts
   with no clean repeated signature) should stay `rawHtml`. The knob + the two gates
   (composability + ground-truth) bound it; the default should favour fidelity (promote only
   when pixel-verified).
