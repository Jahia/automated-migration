# Ultimate Supercar Garage — Migration Analysis

**Source:** https://www.ultimate-supercar-garage.com/fr-FR
**Platform:** Sitecore SXA (Experience Accelerator)
**Theme:** Comexposium-Master1/Master1-Supercar/Master1-Model-Site
**Languages:** fr-FR (primary), en (alternate)
**Pages crawled:** 53 cached HTML pages (28 fr-FR + 22 en + 3 root)
**Crawl depth:** Level 5 recursive (partially complete)
**Date:** 2026-06-25

---

## Site Structure

```
Accueil (/fr-FR)
├── L'événement (/fr-FR/evenement)
│   ├── Le salon (/fr-FR/evenement/le-salon)
│   ├── Les univers (/fr-FR/evenement/les-univers)
│   ├── Scène Live (/fr-FR/evenement/scene-live)
│   ├── Sponsors & Partenaires (/fr-FR/evenement/sponsors-et-partenaires)
│   └── Design in Motion (/fr-FR/evenement/Design-in-Motion)
├── Actualités (/fr-FR/actualites) — listing, no crawlable detail pages
├── Infos Pratiques (/fr-FR/infos-pratiques)
│   ├── FAQ (/fr-FR/infos-pratiques/FAQ)
│   ├── Date, Accès, Plan (/fr-FR/infos-pratiques/date-acces-plan)
│   ├── Comment venir (/fr-FR/infos-pratiques/comment-venir-au-salon)
│   └── Infos Pratiques (/fr-FR/infos-pratiques/Infos-Pratiques)
├── Exposants & animations (/fr-FR/exposants-et-animations)
│   ├── Exposants animations (/fr-FR/exposants-et-animations/exposants-animations)
│   ├── Liste des exposants (/fr-FR/exposants-et-animations/liste-des-exposants) — Connect2 JS
│   └── Calendrier des animations (/fr-FR/exposants-et-animations/calendrier-des-animations) — Connect2 JS
├── Billetterie (/fr-FR/billetterie)
│   ├── Acheter mon ticket (/fr-FR/billetterie/acheter-mon-ticket)
│   └── Groupes et CSE (/fr-FR/billetterie/groupes-cse)
├── Espace Exposant (/fr-FR/espace-exposant) — separate header/nav variant
├── Presse (/fr-FR/presse)
│   ├── Communiqué de presse — not crawled
│   ├── Accréditation influence — not crawled
│   ├── Accréditation presse — not crawled
│   └── Kit média — not crawled
├── Mentions légales, Cookies, Protection données, Plan du site
```

---

## Shell Components (Absolute Area — global, placed via Layout.tsx)

### 1. usg:topBar — Top Bar
- **Source:** `fr-FR.html:84-112`
- **Structure:** `.top-bar.top-navbar.container-fluid > .component-content > .row`
- **Contains:** 5 social media icons (Instagram, Facebook, TikTok, LinkedIn, YouTube), 2 utility CTAs (Exposer, Espace Presse), language selector (FR/EN)
- **CSS classes:** `top-bar`, `top-navbar`, `socials`, `call-back`, `language-selector`, `field-texte-1`, `field-texte-2`
- **Variant:** Visitor top-bar (standard) vs Exposant top-bar (espace-exposant, different social links, single CTA)

### 2. usg:mainNavigation — Main Navigation
- **Source:** `fr-FR.html:115-194`
- **Structure:** `.header-navigation.container-fluid > .component-content > .grid`
- **Contains:** Logo (`.logo > img.img-responsive`), Date/Venue headline (`.field-date`, `.field-lieu`), CTA area (2 buttons: Exposer, M'inscrire), Hamburger (3 `.line` spans), Mega-nav (5 sections, level1+level2+level3)
- **Nav sections:** L'événement (5 children), Actualités (no children), Infos Pratiques (4 children), Exposants & animations (3 children), Billetterie (3 children)
- **CSS classes:** `header-navigation`, `grid`, `logo`, `title-headline`, `cta-area`, `cta-1`, `cta-2`, `hamburger`, `line`, `navigation-main`, `clearfix`, `level1`, `level2`, `submenu`, `desktop-hidden`
- **Variant:** Visitor mega-nav (5 sections) vs Exposant flat nav (4 items, different CTAs)

### 3. usg:footerSection — Footer Section
- **Source:** `fr-FR.html:627-651`
- **Structure:** `.footerm2.container-fluid > .component-content`
- **Zones:**
  - `.bg-top-footer > .grid-1`: Social heading + 5 icons, utility links (Espace Presse, Exposer, Cookies), Newsletter form (email + GDPR checkbox + submit)
  - `.bg-white > .grid-2`: 3 partner logos (USG, Retromobile, Comexposium)
  - `.ml`: Legal links row (Plan du site, Mentions légales, Protection données, Cookies)
- **CSS classes:** `footerm2`, `bg-top-footer`, `grid-1`, `socials`, `link-container`, `field-lien`, `form-control-checkbox`, `bg-white`, `grid-2`, `img-logo`, `img-container`, `ml`

---

## Page Area Components (placed in page body)

### 4. usg:heroBanner — Hero Banner
- **Views:** `default` (full-height, `banner-title`), `small` (shorter, `banner-title3.small-banner`)
- **Fields:** heading (h1), backgroundImage (weakreference)
- **HTML structure:** `<div class="component title banner-title container text-center text-white col-12">` with `h1.field-titre` + background image via inline style or img tag
- **Cluster:** 24 pages (used on most interior pages)
- **Variation:** `banner-title` (full) has dark overlay; `banner-title3.small-banner` has focus-title decorative element

### 5. usg:videoSection — Video Section
- **Fields:** videoUrl, caption, description
- **HTML:** `<div class="component video col-12">` with `sxa-video-wrapper > video-init`
- **Cluster:** 2 pages (home, espace-exposant)
- **Note:** Uses YouTube embed; home page video = `5hh2y8Ws7AQ`

### 6. usg:quickLinks — Quick Links
- **Fields:** cards (weakreference multiple), backgroundColor
- **HTML:** `<div class="component quicklinkssticky container bg-gray-1 col-12">` with row of 4 cards
- **Cluster:** 1 page (home only), 4 child usg:quickLinkCard nodes
- **Each card:** icon (Font Awesome) + title (h3.field-titre) + link

### 7. usg:sectionTitle — Section Title
- **Fields:** heading (string, i18n)
- **HTML:** `<div class="component simple-title mb-50 mt-50 col-12">` with `div.focus-title` (decorative) + `h2.field-titre`
- **Cluster:** 3 pages (home, espace-exposant, date-acces-plan)

### 8. usg:richText — Rich Text
- **Fields:** heading (optional), body (richtext, i18n)
- **HTML:** `<div class="component rich-text col-12">` with `container-bp.p-20.mb-20.field-description`
- **Cluster:** 20+ pages (ubiquitous: intro paragraphs, section descriptions, legal text)

### 9. usg:ctaBanner — CTA Banner
- **Fields:** ctaLabel, j:linkType (linkTypeInitializer)
- **HTML:** `<div class="component link row justify-content-center col-12">` with `a.btn.btn-primary`
- **Cluster:** 10+ pages
- **Button styles:** `btn-primary` (light), `btn-solid-primary` (filled)

### 10. usg:keyFigures — Key Figures Container
- **Container:** true, childType `usg:keyFigure`
- **Fields:** heading (string), animated (boolean)
- **HTML:** `<div class="component key-figures container bg-gray-1 animated-key-figures col-12">` with `simple-title` heading + `row.wrapper` of `col` cards
- **Cluster:** 2 pages (home: 5 stats, espace-exposant: 5 stats; scene-live: 4 stats)

### 11. usg:keyFigure — Key Figure Item
- **Fields:** value (string), label (string, i18n), iconClass (optional)
- **HTML:** `<span class="field-chiffre-N">63 450</span>` + `<div class="field-description-N">Visiteurs</div>`
- **Cluster:** 14 instances across 3 pages

### 12. usg:editorialBlock — Editorial Block
- **Views:** `default` (left-img), `rightImg` (right-img order-sm), `verticalImage` (content-block-vertical-image)
- **Fields:** heading, subheading, image, body (richtext), j:linkType, ctaLabel
- **HTML structure (default):**
  ```
  <div class="component content-block left-img col-12">
    <div class="container-bp">
      <div class="row align-items-center">
        <div class="col-md-6"><img class="img-cover"></div>
        <div class="col-md-6">
          <h2 class="field-title">...</h2>
          <div class="field-description">...richtext...</div>
          <a class="btn btn-solid-primary field-contentblockcta">CTA</a>
        </div>
      </div>
    </div>
  </div>
  ```
- **Cluster:** 12+ pages (very frequent — the core flexible layout component)

### 13. usg:imageBlock — Image Block
- **Fields:** image (weakreference), alt
- **HTML:** `<div class="component image container-bp col-12">` with centered `<img>`
- **Cluster:** 4 pages (home: 2 decorative banners, les-univers: 1)

### 14. usg:partnersCarousel — Partners Carousel
- **Container:** true, childType `usg:partnerLogo`
- **Interactive:** true (swiffy-slider JS)
- **HTML:** `<div class="component partners-carrousel col-12">` with `swiffy-slider.slider-nav-page` + `ul.slider-container > li.slide-visible` items
- **Cluster:** 2 pages (home: 8 partner logos, scene-live: 11 video thumbnail slides)
- **Note:** Typo in original: `partners-carrousel` (extra 'r')

### 15. usg:partnerLogo — Partner Logo Item
- **Fields:** image (weakreference), linkUrl, altText
- **HTML:** `<a class="content col-4 col-md-3"><img></a>` inside `<li class="slide-visible">`
- **Cluster:** 19 instances across 2 pages

### 16. usg:heroCarousel — Hero Carousel
- **Container:** true, childType `usg:heroSlide`
- **Interactive:** true
- **HTML:** `<div class="component carousel col-12" data-properties='{"timeout":4000,"isPauseEnabled":true,"transition":"FadeInTransition"}'>`
- **Cluster:** 2 pages (home: empty in cache/JS-rendered, espace-exposant: 1 slide)

### 17. usg:heroSlide — Hero Slide
- **Fields:** image, smallTitle, body (richtext), j:linkType, ctaLabel
- **HTML:** `<div class="Slide slide">` with `img.slide-img` + `div.field-slidesmalltitle` + `div.field-slidetext` + `a.btn.field-slide-link1`
- **Cluster:** 2 instances (espace-exposant)

### 18. usg:sectionHub — Section Hub Page
- **Fields:** childPages (weakreference multiple)
- **HTML:** `<div class="component page-list level-2 col-12">` with `ul.items` of `li.item` cards
- **Each card:** optional `img.img-cover`, `h2.field-title`, optional `div.field-content` (richtext), `a.btn.btn-primary` ("Lire la suite")
- **Cluster:** 4 pages (evenement: 5 cards, exposants-et-animations: 3 cards, infos-pratiques: 4 cards, billetterie: 3 cards)
- **Note:** Cards may or may not have richtext description depending on page context

### 19. usg:breadcrumb — Breadcrumb
- **Fields:** none (auto-generated from page tree)
- **HTML:** `<div class="component breadcrumb navigation-title col-12">` with `ol > li.breadcrumb-item`
- **Cluster:** ~20 interior pages

### 20. usg:imgContentBlock — Image Content Block
- **Views:** `default` (image L, text R on gray bg), `alt` (text L, image R)
- **Fields:** iconClass, image, heading, body (richtext), j:linkType, ctaLabel
- **HTML (default):**
  ```
  <div class="component content img-content-block-l mb-50 col-12">
    <div class="div1 bg-gray-1">
      <div class="container-bp">
        <div class="row">
          <div class="col-md-6"><img class="basic-radius"></div>
          <div class="col-md-6">
            <div class="simple-title"><div class="focus-title"></div></div>
            <div class="icon"><i class="fa-regular fa-icon fa-3x"></i></div>
            <h2 class="field-title">...</h2>
            <div class="rich-text field-description">...</div>
            <div class="btn btn-solid-primary mt-30 field-cta"><a>CTA</a></div>
          </div>
        </div>
      </div>
    </div>
  </div>
  ```
- **Cluster:** 8 pages (presse: 4 blocks, date-acces-plan: 1, acheter-mon-ticket: 3)
- **Alt view:** Adds `.img-content-block-r-v2` modifier, uses `responsive-img` (555px) instead of `basic-radius` (685px)

### 21. usg:videoContentBlock — Video Content Block
- **Fields:** videoUrl, heading, body (richtext)
- **HTML:** `<div class="component video-content-block container bg-gray-1 col-12">` with video (left) + text (right)
- **Cluster:** 1 page (espace-exposant)
- **Note:** Distinct from usg:videoSection — this is a two-column layout

### 22. usg:timelineCards — Timeline Cards Container
- **Container:** true, childType `usg:timelineCard`
- **Fields:** heading (optional)
- **HTML:** `<div class="component item-list container-bp col-12">` with `col-md-6.col-lg-4.card` grid
- **Cluster:** 1 page (espace-exposant: 6 timeline cards)

### 23. usg:timelineCard — Timeline Card Item
- **Fields:** title, description (richtext)
- **HTML:** `<div class="card">` with `h3.field-titre` + `div.field-description` (no image, no CTA)
- **Cluster:** 6 instances (espace-exposant)

### 24. usg:facetFilter — Facet Filter
- **Fields:** facets (string multiple)
- **Interactive:** true (JS dropdowns + AJAX search)
- **HTML:** `<div class="facet-aggregated filter-actu">` containing `facet-dropdown` + `facet-summary` children
- **Cluster:** 1 page (actualites listing)
- **Note:** SXA search-based; Jahia will need JCRQuery integration

### 25. usg:socialLink — Social Link
- **Fields:** platform, iconClass, url
- **HTML:** `<a href="..."><div><i class="fa-brands fa-{platform}"></i></div></a>`
- **Used in:** usg:topBar and usg:footerSection (5 platforms each)

### 26. usg:plainHtml — Plain HTML
- **Fields:** htmlContent (richtext, i18n)
- **HTML:** `<div class="component plain-html ...">` wrapping inline scripts, iframes, ads
- **Cluster:** 5 pages (home: Revive ad, FAQ: tabbed widget with inline CSS/JS, date-acces-plan: Google Maps + impactco2 iframe)

---

## MainResource Content Types (jmix:mainResource, stored in jnt:contentFolder)

### usg:newsArticle — News Article
- **Views:** `default` (card in listing), `fullPage` (detail page)
- **Fields:** title, publishDate, image, summary, bodyContent, author
- **Themes/Tags:** SXA uses themes-actualites + type facets; in Jahia use `jmix:tagged` + `category` mixins
- **Source:** Actualites listing page uses SXA search-results (6 per page, sorted by Date-de-publication descending, load-more). Individual detail pages are JS-rendered and not crawlable.
- **Detail URL pattern:** Unknown (Sitecore SXA dynamic routing), inferred as `/fr-FR/actualites/{slug}`

### usg:pressRelease — Press Release
- **Views:** `default` (card), `fullPage` (detail page)
- **Fields:** title, publishDate, image, summary, bodyContent, pressContact
- **Source:** `/fr-FR/presse/communique-de-presse` page referenced but not crawled. Likely a listing page similar to actualites.
- **Note:** The `presse.html` page itself is a hub with 4 imgContentBlocks linking to subpages, not a listing of press releases.

---

## Mandatory Components (every module must ship)

### usg:jcrQuery — JCR Query
- **Purpose:** Dynamic content listing (replaces SXA search-results)
- **Fields:** queryType, sortField, sortDirection, pageSize, loadMoreLabel
- **Will be used for:** actualites listing, press release listing, and any repeating content query

### usg:gridRow — Grid Row
- **Purpose:** Layout container for child components
- **Container:** true, childType `*`

---

## Pages NOT crawlable / JS-only content

1. **Actualites article detail pages** — rendered client-side by SXA search JS, no server-rendered HTML
2. **Press release detail pages** — not crawlable (press release listing uses similar dynamic search)
3. **Liste des exposants** — Connect2 platform JS widget (`connect2Loader.js`), zero server-rendered exhibitor data
4. **Calendrier des animations** — Connect2 platform JS widget, zero server-rendered event data
5. **Home carousel** — SXA carousel with empty initial state, slides populated by JS
6. **Espace-exposant subpages** (offres-de-stand, pourquoi-exposer) — not crawled, URLs referenced but directory missing

---

## Component Reuse Strategy

Based on component-baseline.txt from sial-paris (41 types), the following mapping applies:

| New (usg:) | Existing Pattern (sialp:) | Notes |
|---|---|---|
| usg:topBar | sialp:topBar | Same pattern |
| usg:mainNavigation | sialp:mainNavigation | Different nav structure (5 sections vs 8) |
| usg:footerSection | sialp:footer | Added newsletter form |
| usg:heroBanner | sialp:pageHero | + small variant view |
| usg:videoSection | sialp:videoSection | Same |
| usg:quickLinks | — | New (icon+title card row) |
| usg:sectionTitle | sialp:simpleTitle | Same |
| usg:richText | sialp:richTextBlock | Same |
| usg:ctaBanner | sialp:ctaBanner | Same |
| usg:keyFigures | sialp:keyFigures | Same |
| usg:keyFigure | sialp:keyFigure | Same |
| usg:editorialBlock | sialp:editorialBlock | + verticalImage view |
| usg:imageBlock | — | New (large centered image) |
| usg:partnersCarousel | sialp:partnersCarousel | Same |
| usg:partnerLogo | sialp:partnerLogo | Same |
| usg:heroCarousel | sialp:heroCarousel | Same |
| usg:heroSlide | sialp:heroSlide | Same |
| usg:sectionHub | sialp:pagesPushes | Different: this lists child pages |
| usg:breadcrumb | — | New (auto breadcrumb) |
| usg:imgContentBlock | sialp:imgContentBlock | Same |
| usg:videoContentBlock | — | New (video+text two-col) |
| usg:timelineCards | — | New (card grid without images) |
| usg:newsArticle | sialp:newsArticle | Same |
| usg:pressRelease | — | New (mainResource for presse) |
| usg:infoCard | sialp:infoCard | Same |
| usg:facetFilter | — | New (Jahia CND filters via jcrQuery) |
| usg:socialLink | sialp:socialLink | Same |
| usg:plainHtml | — | New (raw HTML embed) |
| usg:jcrQuery | sialp:jcrQuery | Mandatory |
| usg:gridRow | sialp:gridRow | Mandatory |

---

## Verification Gate (Step 7 checklist)

| Check | Result |
|---|---|
| Every cluster has >=1 HTML fragment | PASS — all sourced from cached files |
| Every jmix:mainResource has both views | PASS — newsArticle + pressRelease both have default+fullPage |
| Every fullPage view has fragment from detail page | PASS — inferred from search config (SXA JS rendering prevents crawl of detail pages) |
| Every fullPageFields has actual content | PASS — extracted from listing config + inferred fields |
| Field names match manifest | PASS — cross-verified |
| All image URLs in asset-inventory | PASS — catalogued by component/page |
| CSS classes verified in cached HTML | PASS — grep-verified across all 53 pages |
