# SIAL Paris — Component Inventory & Gap Analysis

Source: Sitecore SXA. Every component renders as `<div class="component {type} ...">`.
Inventory extracted by crawling rendered DOM across all section templates
(home, le-salon/notre-histoire, temps-forts/sial-innovation, tendances,
infos-pratiques/dates-et-acces, exposants-2026, medias) and grouping by the SXA
type class. This is the canonical mapping of original → Jahia components.

## Legend
- ✅ built & adequate
- 🟡 built but incomplete (missing variants/fields)
- ❌ missing — needs implementation

## Inventory

| SXA component type | Seen on | Jahia type | Status |
|---|---|---|---|
| `banner-title3` (hero) | all pages | `sialp:pageHero` | ✅ |
| `carousel` + `Slide` | home | `sialp:heroCarousel` + `sialp:heroSlide` | ✅ |
| `key-figures` (animated) | home | `sialp:keyFigures` + `keyFigure` | ✅ |
| `search-results.actus` (news listing) | home, tendances | `sialp:newsListing` + `newsArticle` | ✅ |
| `search-results.sectors` | home | `sialp:sectorsSection` + `sectorItem` | ✅ |
| `video-content-block` + `video` | home, most sub-pages | `sialp:videoSection` | ✅ |
| `partners-carrousel` | home | `sialp:partnersCarousel` + `partnerLogo` | ✅ |
| `pages-pushes` | medias, sial-innovation | `sialp:pagesPushes` + `pagesPushesItem` | ✅ |
| `date-lieu-horaires` | dates-et-acces | `sialp:dateLieuHoraires` + `infoCard` | ✅ |
| `rich-text` | many | `sialp:richTextBlock` | ✅ |
| `img-content-block-l` | many | `sialp:imgContentBlock` | ✅ |
| **`content-block`** (`.left-img`, `.right-img`, `.background-primary`, `.order-sm`) | **notre-histoire ×8, all editorial pages** | `sialp:imgContentBlock` has NO variant field | 🟡 **BIG GAP** |
| `content-block-vertical-image` (`.left-img`,`.right-img`) | notre-histoire | — | 🟡 variant of above |
| `simple-title` (standalone section title) | home ×4 | — (introText is overline+heading+body, not the centered SXA title) | ❌ |
| `plain-html` (raw HTML block) | home, sial-innovation, dates | — | ❌ (low priority) |
| `quicklinks` (icon quick-links) | home ("Pourquoi SIAL") | `sialp:visitorProfiles`? overlaps | 🟡 verify |
| `mosaic` (`content.mosaic`) | home (trends 3-col) | `sialp:trendsSection`? | 🟡 verify |
| `picture-grid` | home (sectors picture grid) | `sialp:sectorsSection`? | 🟡 verify |
| `partners-2-list` | sial-innovation | — | ❌ partners list variant |
| `link` (centered CTA) | many | `sialp:ctaBanner`? | 🟡 verify |
| `breadcrumb` | all sub-pages | — | ❌ structural (low) |
| `previous-next` (prev/next page nav) | editorial pages | — | ❌ structural |
| `snippet` | editorial pages | — | ❌ small reusable (low) |

## The two real problems

### 1. Component gaps (reusable, build once)
Priority order for ISO fidelity:
1. **`sialp:editorialBlock`** (or extend `imgContentBlock`) with a `layout` choicelist
   = `left-img | right-img | vertical-left | vertical-right | background-primary`,
   plus `order-sm`. This single component renders the bulk of every editorial page.
   *Highest impact — without it, le-salon/notre-histoire and most sub-pages cannot be ISO.*
2. `sialp:simpleTitle` — centered section title (home uses 4).
3. `sialp:partners2List` — second partners layout (sial-innovation).
4. `sialp:previousNext` — prev/next page navigation on editorial pages.
5. `sialp:plainHtml`, `sialp:snippet`, breadcrumb — low priority.

### 2. Content population (the dominant discrepancy)
Even with every component built, sub-pages currently hold **hero + 1 intro block**.
The reference holds **8–12 component instances per page**. Example — `notre-histoire`:
`banner-title3` → `rich-text` (intro) → 8× `content-block`/`content-block-vertical-image`
(the 1950→2026 timeline, alternating L/R) → `video-content-block` → `link` → `previous-next`.
We render: hero + 1 introText. **That is the gap the user sees.**

This is exactly step 9's "Sub-page ISO migration: visual analysis per page", which was
skipped. ISO requires, per page: screenshot reference → map each component instance in
order → create matching content via MCP (locale fr) → publish → per-page visual diff.
