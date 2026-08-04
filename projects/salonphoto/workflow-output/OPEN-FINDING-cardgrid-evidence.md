# OPEN: CTA extraction destroys the evidence repeat detection needs

**Status:** unfixed, gate RED, run paused at `step_content_extract`.
**Found:** 2026-08-04, by `probes/reconcile-check.py` (1 violation, blocking).
**Not fixed because:** the correct fix reorders the semanticizer's decomposition
passes, which is core behaviour shared by every project. It deserves a measured
change with the operator present, not a late unattended edit — I had already had
two thrash cycles in this file the same day.

## The violation, verbatim

```
FAIL: reconcile-check — 1 violation(s)
  - VALUE salon_profil-visiteur[3]: body carries 2 top-level raster image unit(s)
    frozen in richtext (must be the image media unit / decomposed children)
```

## What the band actually is

`salon/profil-visiteur` carries the three audience-choice cards (amateur averti /
créateur de contenus / professionnel). The source declares the band as `content`
— its catch-all type — and the instance came out as `sdp:richTextSection` with:

* `skeleton` (520 chars): `div.row` holding `{{child:0}}` **and two more cards
  inline** as `<a href=".../createur-contenus"><div class="card">…`, with the
  image slots (`div.field-image-push`) EMPTY;
* `children`: 1 (`sdp:cta`, "Amateur averti");
* `fields.body` (1350 chars): all three cards' prose AND both remaining images —
  and it is **unpaired** (no `{{f:body}}` marker in the skeleton), so as it stands
  that copy renders nowhere at all.

So the band is a half-decomposed card grid. The model it should reach is
`sdp:cardGrid` with three `sdp:cardItem` children, each carrying its own title,
body, image and cta.

## Why it typed as prose

`_structural_type` calls a band a cardGrid on `len(kids) >= 3`. CTA extraction had
already run and turned three sibling cards into **two inline elements + one child
marker**, so the count was 1 and the band fell through to the `has_body` branch.
The evidence the repeat test needs is consumed before the test runs.

## Why no other check caught it earlier

`_debodify_images` skips any body value whose `{{f:body}}` marker is absent from
the skeleton — "unpaired value — the slot gates own that class". No slot gate
actually owns an unpaired body carrying top-level rasters, so the images sat
frozen and unclaimed until reconcile-check looked. Two rules that each defer to
the other leave a hole; that is worth fixing regardless of the ordering above.

## Recommended fix (for review)

1. Detect the repeat BEFORE extracting CTAs/atoms, or count `{{child:N}}` markers
   as siblings when measuring the repeat, so three cards read as three units
   whichever pass touched them first.
2. Close the deferral hole: an unpaired body with top-level raster units must be
   owned by SOMETHING — either paired by `_normalize_slots` before the image
   sweep, or dropped as a dead shadow copy if its text is already in the
   skeleton. Here it is neither: the text is unique and unrendered.

## Scope of the impact, measured

One band on one of 27 pages. Every other page reconciles (`reconcile-check`:
4581/4581 source words), and the rest of the analyze phase is green:
capture-slugs, mirror-registry, mirror-selfcontained, entity-coverage,
link-census (15989 links), census-coverage, zone-source, entity-payload (237
details: 0 titleless, 0 bodiless, 0 thin, 0 flat), sxa-coverage 41/41,
archetype-utilization (6 live types, no concentration), inventory-coverage
(0.97 headings / 0.99 images), type-closure (549 instances, all declared).

Do NOT patch `_debodify_images` to lift these two images on its own: that would
turn the card grid into a rich-text band with three loose media units and make the
gate green over the wrong model.
