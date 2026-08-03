# Salon de la Photo — zoning map + component model

**For review at `step_model_author`.** Source `https://www.lesalondelaphoto.com/fr-FR`
(Sitecore SXA, fr only) → Jahia site `salonphoto`, ns `sdp`/`sdpmix`.
Machine twin: `component-model.json`. Entity map: `orchestration/content/salonphoto.mainresource.json`.

Everything below is measured. Nothing is inferred from what the site "probably" does.

| evidence | value | producer |
|---|---|---|
| menu pages captured | 27 (fr-FR only, 0 failed, 1 utility skipped) | `nav_scope_crawl` |
| source declares its components | **36 types** | `declared_inventory` (SXA adapter) |
| zone regime / DOM coverage | framework-semantic classes / **99%** | `zone_detect` (scoped mirror) |
| content bands | 207 across 27 pages (min 3/page) | `model_census` |
| interactive behaviours | 6 kinds, 47 instances | `island_probe` |
| arrangement clusters | 5 | `zone_detect` |

---

## 1. Zoning map

### ABSOLUTE — site chrome (every page)

`Nav` · `Header` · `Footer` + the footer's own rows (`Socials`, newsletter `Grid 1`,
logo `Grid 2`, link column `Ml`). All 27/27 pages.

> This tier only became truthful after scoping. Before excluding OneTrust, **20+ of 35
> "ABSOLUTE" keys were the cookie banner** (`Ot Grp Hdr1`, `Ot Sdk Row`, `Ot Pc Scrollbar`,
> `Dialog`, `Ot Chkbox`) — the map was reading a consent widget as site chrome. Excluding it
> also collapsed the arrangement clusters from 21 to 5, because the banner was drowning the
> template signal.

### TEMPLATE — 0 keys

Expected on this source: one SXA page design serves every inner page, so "which components
appear" barely separates templates. Role tells do the work instead (§2).

### RECORD — repeating siblings (the card/list tier)

| key | max siblings | reading |
|---|---|---|
| `Component` | 31 | generic SXA component repeat — the band level itself |
| `Level2` | 6 | mega-menu children |
| `Lien` | 6 | footer link column |
| `Title` | 3 | listing card titles |
| `Breadcrumb Item` | 3 | breadcrumb trail |
| `Item` → `Card` | 10 | **the listing cards** (9 pages) — articles, agenda, programme |

### COMPONENT tier — a caveat worth knowing

It is dominated by SXA **field** wrappers (`Navigationtitle` x798, `Component Content` x490,
`Texte`, `Date`, `Lieu`), not components. That is correct behaviour for tier-2 signal on SXA
(`field-*` classes), and it is exactly why the **declared** inventory carries the component
identity on this source while `zone_detect` contributes scope + records.

---

## 2. Templates — 3, by role

| template | pages | the tell (measured) |
|---|---|---|
| `home` | 1 | the **only** page with 0 breadcrumbs and the only `.component.carousel` |
| `standard` | 26 | breadcrumb 26/26 + a `.component.title` banner 25/26 + one main column; 22 in one arrangement cluster |
| `MainResource` | 0 crawled | renders an entity at its own URL (article / agenda / programme) |

The 3 singleton clusters (`salon_a-propos`, `salon_partenaires`, `agenda-photo`+`photo-pass`)
differ by **content mix, not skeleton** → they stay on `standard`. A 4th template would cost a
governance contract and buy nothing.

Page-size spread, for area governance: `infos-pratiques_faq` 33 bands, `comment-venir-au-salon`
16, `lien-billetterie` 14, `qui-expose` 13, `home` 12 … down to 3 for the section landings.
So `main` is an **OPEN** surface led by `sdp:cols`, not a narrow slot.

---

## 3. Page components — 36 declared types → 13 Jahia types

One type, many views. The collapse ratio is the point.

| Jahia type | views | absorbs (SXA) | measured |
|---|---|---|---|
| `sdp:richTextSection` | default, intro | `content`, `rich-text`, `page-list` | 151 of 207 bands are signature `plain`; `content` x122 |
| `sdp:cardGrid` (+`sdp:cardItem`) | default, **carousel**, pictureGrid, logoWall | `picture-grid`, `carousel`+`Slide`, `partners-carrousel`, `partners-2-list`, `quicklinks` | 5 different repeating-tile components collapse here |
| `sdp:banner` | default, hero | `title`, `banner2`, `simple-title` | `title` x25 (the page-title banner) |
| `sdp:jcrQuery` | default, grid, inline | `search-results`, `page-list`, `event-list`, `load-more`, **all facet-\*** | x10 + x8 |
| `sdp:accordion` (+`sdp:accordionItem`) | default | `accordion`, `tabs` | x8 (all on FAQ) + x2 |
| `sdp:mediaText` | default (+`layout` imageLeft/Right) | `content-block`, `content-block-vertical-image` | x5 |
| `sdp:statCallout` | default | `date-lieu-horaires`, `key-figures` | x1 (3 title/description pairs) |
| `sdp:layoutSection` | default | `container`, `snippet` | x20 |
| `sdp:cols` | default | — (SXA uses Bootstrap classes) | required by rule 16 regardless |
| `sdp:subNavigation` | default | `page-list` (tree-driven instances) | confirm per instance |
| `sdp:siteHeader` | default | `top-bar`, `header-navigation` | 27/27 |
| `sdp:mainNavigation` | default | `navigation` | 27/27, tree-driven |
| `sdp:footer` (+`sdp:footerLink`) | default | `footer` | 27/27 |

**10 declared types deliberately ignored**, each with a reason on the record (`sxaIgnored` in
the JSON): `plain-html`, `image-de-fond`, `breadcrumb`, `snippet`, `previous-next`, `link`,
`navigationtitle`, `structured-data`, `container`, `load-more`. No silent drops —
`sxa-coverage.sh` fails on any declared type that is neither mapped nor ignored.

---

## 4. mainResource components — the entity split

**The rule:** nav-reachable = page; card-reached dated prose = entity; ties break to page.
None of the prefixes below is in the source menu; every card carries a date + a badge + a title.

| folder | type | detail URLs found | listing page |
|---|---|---|---|
| `contents/actualites` | `sdp:newsArticle` | 9 under `actualite-photo/actus` | `actualite-photo_actus` |
| `contents/agenda` | `sdp:event` | 20 under `actualite-photo/agenda-photo` | `actualite-photo_agenda-photo` |
| `contents/programme` | `sdp:event` | **37** under `animations-ateliers/programme-salon/Evenement` | `animations-ateliers_programme-salon` |
| `contents/expositions` | `sdp:event` | 9 — *open question* | `animations-ateliers_expositions-photos` |
| `contents/animations` | `sdp:event` | 6 — *open question* | `animations-ateliers_animations` |

Two types, five folders. Agenda and programme events share one field surface, so they are one
type (two types with the same shape would fail `dup-shapes.sh`).

The programme cluster is the biggest and was **invisible to a link sweep** of its listing (the
programme renders inside tabs/accordion): only the census's uncrawled-prefix ledger surfaced
its 37 links. Worth remembering as a method note.

Badges (`Actualités`, `Professionnels`, `Amateurs`, `Agenda`, `Expositions`) are **Jahia
categories**, never CND fields.

---

## 5. Islands — behaviours the source ships in JS

The migration drops source JS on purpose, so each behaviour is an explicit decision.

| behaviour | where | decision |
|---|---|---|
| **hero carousel** | home, 1 | **ADOPT `SxaCarousel`** — `div.carousel-inner > ul.slides > li.slide`, controls `a.prev-text`/`a.next-text`, `data-properties` autoplay 4000ms + pause-on-hover + FadeInTransition |
| **partners carousel** | home, 1 | **ADOPT `SwiffySlider`** — `ul.slider-container > li.row`, `button.slider-nav`, 4 indicator buttons; vendor the jsdelivr CSS |
| collapsible | 10 (FAQ x8, tabs x2) | ADOPT one island on `sdp:accordion`; render flat in edit mode |
| **facet filter** | 11 on 2 pages | **REPLACE, not port** — `/sxa/search` has no Jahia backend; becomes `sdp:jcrQuery` + categories + client-side chips |
| newsletter form | 27 (footer) | ADOPT minimal, one footer instance |
| video player | 2 | STATIC `<iframe>` (never `<video><source type="video/youtube">`) |
| map | 1 | STATIC `<iframe>`, kept embed |
| modal/popin | 5 | DEFER — decide once detail pages are crawled |

> The island the harness already ships (`SourceCarousel`) targets Embla
> `[data-slot="carousel"]` from SingPost and **will not attach to either** of these. Two new
> islands, not one reused.

---

## 6. Scope decisions on the record

**Excluded** (each measured before deciding): OneTrust consent + its `cdn.cookielaw.org` loader
(27/27) · Cloudflare RUM beacon + chatbase chatbot + GTM iframe and inline bootstrap · 27
zero-height spacers · 3 JSON-LD-only components.

**Kept embeds** (real content, each a modelling decision): YouTube (home video band) · 2x
Weezevent ticketing (`lien-billetterie`) · Google My Maps (`photo-pass`) · impactco2 transport
calculator (`dates-acces-horaires`) · jsdelivr swiffy-slider CSS (vendor it in `step_assets`).

`probes/mirror-selfcontained.py` now fails on any un-declared remote fetch, including URLs
built at runtime inside inline scripts.

---

## 7. What I need from you

1. **Exhibitor catalogue** (`/infos-pratiques/catalogue`, + an uncrawled `/exposants`): entity
   folder, editorial page linking out, or out of scope? Its list is not in the captured DOM.
2. **`expositions-photos` (9) and `animations` (6)**: entities or sub-pages? The rule breaks
   ties to page; 2 sample crawls settle it.
3. **Ticketing** `/fr-FR/billet` was skipped as a utility URL by the crawler's default. "Acheter
   mon billet" is the site's primary CTA — confirm that is intended.
4. **A detail-page crawl is required** before `load_main_resources` (~87 entity URLs). It also
   completes the declared inventory: this run sees 36 types, the 2026-06 corpus saw 42 — the 6
   extras (`image-content-block-description`, `key-figures`, `anchors-links`,
   `item-content-popin-picture`, `event-list`, `video`) live on detail pages.
5. **`orchestration/content/salonphoto.mainresource.json` must exist before the plan is
   regenerated** — `gen_plan` decides at generation time whether `step_main_resources` and the
   `startnode` gate exist at all. It exists now; the plan must be regenerated after you approve
   this model, or structured content is silently dropped from the run.
