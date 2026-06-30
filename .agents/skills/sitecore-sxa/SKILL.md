---
name: sitecore-sxa
description: Detect a Sitecore SXA source site and extract its COMPLETE component inventory deterministically from the DOM, so analysis never silently drops components. Sitecore declares every component as `.component <type>` + `.component-content` + `field-*`; walk that instead of eyeballing the render. Run during analysis (phase 1) BEFORE building the component manifest.
type: technical
phase: 1
status: active
allowed-tools: Bash, Read, Write
---

# Skill: Sitecore SXA — deterministic component extraction

## Why this exists

The #1 analysis defect on Sitecore migrations is **silently dropped components**.
The analyze step had the LLM *look at the rendered page and cluster what it sees* —
which is incomplete (it overlooks small/peripheral blocks: a `top-bar` strip, a
`contact-block` newsletter, `key-figures`, an `accordion`) and non-reproducible (one
run captures a TopBar, the next doesn't). On lesalondelaphoto the LLM manifest had
**14** components; the source actually had **42**.

But Sitecore SXA **declares every component in the DOM**, so discovery should be
deterministic, not guessed:

```
<div class="component <TYPE> …">       ← one component instance. The class after
   <div class="component-content">     ← 'component' (minus bootstrap/layout utils)
      …class="field-<NAME>"…           ← is the type. Each field-* = one property.
```

This is the contract: **component → component-content → field-\* become properties**,
and a `.component` whose content holds repeated child `.component`s is a container
(carousel / grid / list) with a child type.

## When to run

Phase 1 (analyze), **before** writing `component-manifest.json` — and again as a gate
after, so coverage is enforced. The harness stays source-agnostic: this only fires
when the source is detected as SXA.

## Step 1 — Detect Sitecore SXA

A captured page is SXA if it has `class="component "` + `component-content` + `field-*`,
and typically `/-/media/` asset URLs and the Bootstrap-4 / Core-Libraries /
`*-Model-Site` theme CSS. Quick check:

```bash
grep -lq 'component-content' projects/<p>/.reference/cache/_crawl/**/*.html && echo "SXA"
```

## Step 2 — Extract the complete inventory (deterministic)

```bash
python3 orchestration/lib/sxa-extract.py projects/<p>/.reference/cache > projects/<p>/.reference/sxa-components.json
```

Output per component type: `type`, `aliases`, `fields[]`, `childTypes[]`,
`isContainer`, `instances`, `pages[]`. This is the **complete** component surface —
use it as the seed for the manifest. Your job shifts from *discovering* components
(unreliable) to *modelling* them into Jahia (your strength).

## Step 3 — Map SXA → Jahia (component-manifest.json)

For EVERY extracted type, decide one of:

- **Model it** — add a Jahia component (or a view on an existing one) and record the
  source on it: `"sxaSource": ["<sxa-type>", "<alias>"]`. `field-<name>` → a property
  (camelCase the name; default user-visible strings to `i18n`; links →
  `j:linkType` choicelist[linkTypeInitializer]; images → weakreference `< jmix:image`;
  tags/categories → built-ins). A container type → `jmix:list` + a child type.
- **Reuse a view** — same data shape, different markup → an extra `*.server.tsx` view
  on an existing type (still record `sxaSource`).
- **Skip it** — generic/structural/template-level (see vocabulary) → add to the
  top-level `"sxaIgnored": ["<sxa-type>"]` **with a reason in a comment/field**.

No silent drops: every extracted type is mapped or ignored.

### Step 3b — a "field" is not always a property: field vs child vs mixin

The extractor's `field-*` list is a starting point, not the final model. Decompose each
component's content into the right Jahia construct:

- **Property** — a single scalar/text/image/link field → a CND property.
- **Child component (a SERIES)** — a *repeating* set of links or items is NOT flat
  fields; it's `+ * (ns:childType)` on a `jmix:list` container. The extractor flags
  these: `linkSeries`/`listItems` counts + `hasIcons` + a `modelHint`. Examples:
  - top-bar's 5 social links (`hasIcons: fa-instagram, fa-facebook-f…`) → a reusable
    **`ns:socialLink`** child (`platform`/`icon` + `j:linkType` external), not
    `texte/texte-1/texte-2`.
  - footer link columns, nav items, partner logos, card grids, key-figure stats,
    accordion panels → each a child type under a `jmix:list` container.
  - The CTA links ("Devenir exposant" + url) repeated across top-bar/hero/cards →
    `ns:ctaButton` children.
  - CAVEAT: a high `linkSeries` on `rich-text`/`content` is usually **inline links in
    prose**, not a child series — judge by context (the hint is a signal, not a rule).
- **Mixin** — a field GROUP that recurs across many components (link+label,
  image+alt+caption, social block, SEO meta) → extract a module mixin
  (`nsmix:cta`, `nsmix:media`, `nsmix:socials`) and have the types extend it, instead
  of re-declaring the fields on each (matches the migration mixin-reuse rule).

Rule of thumb: **one of something → property; many of something → child component;
the same group on many things → mixin.**

### Recurring SXA component vocabulary (3 migrations: supercar, sial-paris, lesalondelaphoto)

| SXA `.component` | Typical Jahia mapping |
|---|---|
| `top-bar` / `top-navbar` | a `topBar` type (social links child + CTA links + search) — a singleton in an AbsoluteArea |
| `header-navigation`, `navigation` | the 3-level `mainNav` (Navigation Menu over the page tree) |
| `footer` | `footer` singleton (links + newsletter + socials) |
| `rich-text`, `content`, `simple-title`, `content-block`, `content-block-vertical-image`, `image-content-block-description` | `editorialBlock` + views (default / sectionTitle / image-left / image-right) |
| `carousel` + `Slide`, `banner2` | `heroCarousel` (container) + `hero` (slide) |
| `picture-grid` | `cardGrid` (container) + card view |
| `partners-carrousel`, `partners-2-list` | `partnerCarousel` (container) + `partnerItem` |
| `video-content-block`, `video` | `promoBlock` / video component (YouTube `<iframe>`, not `<video>`) |
| `search-results`, `page-list`, `event-list`, `load-more`, `facet-*` | `jcrQuery` listing (Jahia has **no** SXA facet backend — categories + chips replace facets) |
| `contact-block` | `contactBlock` (newsletter / contact fields) |
| `key-figures` | `keyFigures` (stat items) |
| `accordion`, `tabs` | container + child content type |
| `date-lieu-horaires`, `item-content-popin-picture`, `quicklinks`, `anchors-links` | small info/CTA components or views |
| `breadcrumb` | page-template level (render from the page tree), usually `sxaIgnored` |
| `image-de-fond` / `background-img` | a background-image property on the hosting component, or template-level → often `sxaIgnored` |
| `plain-html`, `snippet`, `previous-next`, `container`, `link` | generic/structural — usually `sxaIgnored` (raw markup widget, article prev/next, layout wrapper, plain link) |

## Step 4 — Gate: coverage is complete

```bash
bash orchestration/probes/sxa-coverage.sh projects/<p>
```

FAILS and names any extracted SXA type the manifest neither maps (`sxaSource`) nor
ignores (`sxaIgnored`). This is the gate that catches a dropped `top-bar` instead of
shipping a site without it. It is wired into the analyze step (skill 01).

## Output

- `projects/<p>/.reference/sxa-components.json` — the deterministic inventory (committed).
- `component-manifest.json` — every component carries `sxaSource`; a top-level
  `sxaIgnored` lists the deliberately-skipped types. `sxa-coverage.sh` PASSES.
