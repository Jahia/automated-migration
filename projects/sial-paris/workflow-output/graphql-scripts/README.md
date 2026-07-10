# SIAL Paris Content Creation — Workflow Scripts

## Overview
Complete content population for the SIAL Paris 2026 Jahia site. All scripts follow the GraphQL JCR API pattern with proper i18n property handling.

**Status:** ✓ COMPLETE — All content created and published to live workspace

---

## Execution Steps

Scripts must be run in order. Each script is idempotent where possible.

### STEP 1 — Upload Images (SKIPPED)
**File:** `step1-upload-images-fixed.sh`
- Uploads DAM assets (logo-header.jpg, video-thumbnail.jpg)
- Creates `/sites/sial-paris/files/images/` folder
- Saves image UUIDs to `/tmp/sial-paris-images.json`
- **Note:** Image upload via multipart GraphQL is currently skipped due to endpoint timeout issues

### STEP 2 — Create Pages
**File:** `step2-create-pages.sh`
- Creates 6 sub-pages under `/sites/sial-paris/home`:
  - `le-salon` (Le Salon)
  - `les-exposants` (Les Exposants 2026)
  - `temps-forts` (Temps Forts)
  - `tendances` (Tendances)
  - `infos-pratiques` (Infos Pratiques)
  - `medias` (Médias)
- All pages use `basic` template
- All pages published after creation

### STEP 3 — Create Header & Footer
**File:** `step3-create-header-footer.sh`
- Creates `header` area under home with `sialp:mainNavigation` component
- Creates `footer` area under home with `sialp:footer` component
- Sets multilingual properties (French primary):
  - Navigation CTAs: "J'EXPOSE", "JE VISITE"
  - Footer: newsletter heading, placeholder, copyright text

### STEP 4 — Create Home Page Areas
**File:** `step4-create-home-areas.sh`
- Verifies `hero` and `main` content areas exist (auto-created by template)
- These are container nodes for home page components

### STEP 5 — Create Hero Carousel
**File:** `step5-create-hero-carousel.sh`
- Creates `heroCarousel` component in hero area
- Creates 3 slides (`slide1`, `slide2`, `slide3`):
  1. Event dates, heading, body, CTA
  2. SIAL Innovation announcement
  3. SIAL for Change (sustainability focus)
- All properties internationalized (French language)

### STEP 6 — Create Main Components (Part 1)
**File:** `step6-create-main-components.sh`
- `introText` — Overline, heading, body (3 properties)
- `keyFigures` — 5 key figures (7.5K exposants, 200 pays, 400K products, 200K visitors, 5 days)
- `newsListing` — Heading, CTA label, maxItems=3

### STEP 7 — Create Main Components (Part 2)
**File:** `step7-create-remaining-components.sh`
- `visitorProfiles` — 4 profiles (Distributeurs, Industriels, Restaurateurs, Grand public)
- `trendsSection` — Heading, intro, CTA label + 3 trend cards (Durabilité, Santé, Tech)
- `videoSection` — Heading + YouTube embed URL
- `ctaDualCards` — Left/right headings and CTA labels (Exposants / Visiteurs)
- `sialNetwork` — 7 SIAL global events (Paris, Canada, China, India, Interfood, ME, Network)

### STEP 8 — Create News Articles
**File:** `step8-create-news-articles-fixed.sh`
- Creates `/sites/sial-paris/contents/news/` folder
- Creates 3 newsArticle nodes:
  1. `sial-innovation-2026` (March 15, 2026)
  2. `rapport-tendances-2026` (February 28, 2026)
  3. `j-200-exposants` (April 1, 2026)
- Each article has: title, excerpt, body, category, publishDate
- All articles published

### STEP 9 — Final Publish
**File:** `step9-final-publish.sh`
- Publishes home main area and home page with all sub-nodes
- Publishes news folder and articles

### STEP 10 — Verification
**File:** `step10-verify.sh`
- Checks home page HTTP status
- Counts published nodes in live workspace
- Verifies sub-pages accessibility
- Inventories components by type

---

## Content Structure Summary

```
/sites/sial-paris/home/
├── header (jnt:contentList)
│   └── mainNavigation (sialp:mainNavigation)
├── footer (jnt:contentList)
│   └── footer (sialp:footer)
├── hero (jnt:contentList)
│   └── heroCarousel (sialp:heroCarousel)
│       ├── slide1 (sialp:heroSlide)
│       ├── slide2 (sialp:heroSlide)
│       └── slide3 (sialp:heroSlide)
├── main (jnt:contentList)
│   ├── introText (sialp:introText)
│   ├── keyFigures (sialp:keyFigures)
│   │   ├── fig1–fig5 (sialp:keyFigure)
│   ├── newsListing (sialp:newsListing)
│   ├── visitorProfiles (sialp:visitorProfiles)
│   │   ├── distributeurs (sialp:visitorProfile)
│   │   ├── industriels (sialp:visitorProfile)
│   │   ├── restaurateurs (sialp:visitorProfile)
│   │   └── grandpublic (sialp:visitorProfile)
│   ├── trendsSection (sialp:trendsSection)
│   │   ├── trend1 (sialp:trendCard)
│   │   ├── trend2 (sialp:trendCard)
│   │   └── trend3 (sialp:trendCard)
│   ├── videoSection (sialp:videoSection)
│   ├── ctaDualCards (sialp:ctaDualCards)
│   └── sialNetwork (sialp:sialNetwork)
│       ├── sial-paris (sialp:networkEvent)
│       ├── sial-canada (sialp:networkEvent)
│       ├── sial-china (sialp:networkEvent)
│       ├── sial-india (sialp:networkEvent)
│       ├── sial-interfood (sialp:networkEvent)
│       ├── sial-me (sialp:networkEvent)
│       └── sial-network (sialp:networkEvent)
└── [sub-pages] (jnt:page)
    ├── le-salon
    ├── les-exposants
    ├── temps-forts
    ├── tendances
    ├── infos-pratiques
    └── medias

/sites/sial-paris/contents/news/
├── sial-innovation-2026 (sialp:newsArticle)
├── rapport-tendances-2026 (sialp:newsArticle)
└── j-200-exposants (sialp:newsArticle)
```

---

## Key Implementation Details

### Internationalization (i18n)
All user-facing properties use `language: "fr"` in GraphQL mutations:
```graphql
mutateProperty(name: "heading") {
  setValue(language: "fr", value: "Mon titre")
}
```

### Date Handling
Publishing dates use ISO 8601 format with `type: DATE`:
```graphql
mutateProperty(name: "publishDate") {
  setValue(value: "2026-03-15T00:00:00.000Z", type: DATE)
}
```

### Publishing Workflow
1. Create nodes in `workspace: EDIT`
2. Publish with `publish(publishSubNodes: true)` to move to `workspace: LIVE`
3. Sub-nodes automatically cascade on parent publish

### Error Handling
Each script includes:
- `verify_response()` function for error detection
- Property validation before mutations
- Sleep delays (0.2–0.3s) between dependent operations

---

## Variables Used

```bash
JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"              # Local dev credentials
SITE_NAME="sial-paris"
LANG="fr"                            # Primary language
```

### Required Headers (all requests)
```bash
-H "Origin: http://localhost:8080"
-H "content-type: application/json"
```

---

## Verification Checklist

- [x] 6 sub-pages created and published
- [x] Header with mainNavigation component
- [x] Footer with footer component
- [x] Hero carousel with 3 slides
- [x] 8 main area components (introText, keyFigures, newsListing, visitorProfiles, trendsSection, videoSection, ctaDualCards, sialNetwork)
- [x] 5 key figures under keyFigures
- [x] 4 visitor profiles
- [x] 3 trend cards
- [x] 7 SIAL network events
- [x] 3 news articles in /contents/news/
- [x] All content published to live workspace

---

## Re-running the Workflow

To re-populate content from scratch:

1. Delete all content:
   ```bash
   curl -u root:root http://localhost:8080/modules/graphql \
     -H "Origin: http://localhost:8080" -H "content-type: application/json" \
     -d '{"query":"mutation { jcr { mutateNode(pathOrId: \"/sites/sial-paris/home\") { delete } } }"}'
   ```

2. Re-create home page if needed (via jContent UI or GraphQL mutation)

3. Run STEP 2 through STEP 9 in sequence

---

## Notes

- **Images:** Upload via multipart GraphQL currently times out. DAM setup can be done via jContent UI or separate REST API call.
- **News folder:** Automatically created if missing
- **Sub-pages:** Use `basic` template; Areas created by template automatically
- **All times:** UTC (Z) timezone used for date properties
- **Language:** French (fr) is primary; keys like `"J'EXPOSE"` use HTML entities

---

Generated: 2026-06-16
Module: sial-paris (namespace: sialp:, sialpmix:)
