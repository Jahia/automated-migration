# SIAL Paris Content Inventory

## Site Information
- **Site Key:** sial-paris
- **UUID:** d654e9e9-2366-4c3c-91a0-a733ac87c776
- **Title:** SIAL Paris
- **Language:** fr (French)
- **Template Set:** sial-paris
- **Publication Status:** PUBLISHED

## Content Tree Statistics
- **Total Pages:** 7 (1 home + 6 sub-pages)
- **Total Components:** 35+
- **Total Uploaded Images:** 2
- **Publication Status:** All PUBLISHED to live workspace

## Detailed Content Map

### /sites/sial-paris (Root)
├── home (jnt:page) [PUBLISHED]
│   ├── header (jnt:contentList)
│   │   └── navigation (sialp:mainNavigation)
│   │       └── exposantCtaLabel: "Je suis exposant"
│   │       └── visiteurCtaLabel: "Je suis visiteur"
│   │       └── logoImage: UUID f5c9f9bc-9909-40ef-af49-9873462de461
│   │
│   ├── footer (jnt:contentList)
│   │   └── footer-content (sialp:footer)
│   │       └── newsletterHeading: "Restez informé"
│   │       └── newsletterPlaceholder: "Votre adresse email"
│   │       └── copyrightText: "© 2026 SIAL Paris - Comexposium"
│   │       └── sialLogo: UUID f5c9f9bc-9909-40ef-af49-9873462de461
│   │
│   ├── hero (jnt:contentList)
│   │   └── hero-carousel (sialp:heroCarousel)
│   │       ├── slide-1 (sialp:heroSlide)
│   │       ├── slide-2 (sialp:heroSlide)
│   │       └── slide-3 (sialp:heroSlide)
│   │
│   ├── main (jnt:contentList)
│   │   ├── intro (sialp:introText)
│   │   ├── key-figures (sialp:keyFigures)
│   │   │   ├── fig-1 (sialp:keyFigure): 7 500 exposants
│   │   │   ├── fig-3 (sialp:keyFigure): 400 000 produits
│   │   │   ├── fig-4 (sialp:keyFigure): 200 000 visiteurs
│   │   │   └── [fig-2 & fig-5 had constraint issues - recreate if needed]
│   │   ├── news-section (sialp:newsListing)
│   │   ├── visitor-profiles (sialp:visitorProfiles)
│   │   │   ├── distributors (sialp:visitorProfile)
│   │   │   ├── manufacturers (sialp:visitorProfile)
│   │   │   ├── restaurateurs (sialp:visitorProfile)
│   │   │   └── public (sialp:visitorProfile)
│   │   ├── trends-section (sialp:trendsSection)
│   │   │   ├── card-1 (sialp:trendCard): Durabilité
│   │   │   ├── card-2 (sialp:trendCard): Santé
│   │   │   └── card-3 (sialp:trendCard): Tech
│   │   ├── video-section (sialp:videoSection)
│   │   │   └── thumbnailImage: UUID 060d468c-52c5-4e8e-84f8-7dcf7f5de291
│   │   ├── cta-cards (sialp:ctaDualCards)
│   │   └── network-events (sialp:sialNetwork)
│   │       ├── event-1 (sialp:networkEvent): SIAL Paris
│   │       ├── event-2 (sialp:networkEvent): SIAL Canada
│   │       ├── event-3 (sialp:networkEvent): SIAL China
│   │       ├── event-4 (sialp:networkEvent): SIAL India
│   │       ├── event-5 (sialp:networkEvent): SIAL Interfood
│   │       ├── event-6 (sialp:networkEvent): SIAL Middle East
│   │       └── event-7 (sialp:networkEvent): SIAL Network
│   │
│   ├── le-salon (jnt:page) [PUBLISHED]
│   │   └── main (jnt:contentList)
│   ├── les-exposants (jnt:page) [PUBLISHED]
│   │   └── main (jnt:contentList)
│   ├── temps-forts (jnt:page) [PUBLISHED]
│   │   └── main (jnt:contentList)
│   ├── tendances (jnt:page) [PUBLISHED]
│   │   └── main (jnt:contentList)
│   ├── infos-pratiques (jnt:page) [PUBLISHED]
│   │   └── main (jnt:contentList)
│   └── medias (jnt:page) [PUBLISHED]
│       └── main (jnt:contentList)
│
├── files (jnt:folder)
│   └── images (jnt:folder) [PUBLISHED]
│       ├── logo-header.jpg (jnt:file, jmix:image)
│       │   └── UUID: f5c9f9bc-9909-40ef-af49-9873462de461
│       └── video-thumbnail.jpg (jnt:file, jmix:image)
│           └── UUID: 060d468c-52c5-4e8e-84f8-7dcf7f5de291
│
└── actualites (jnt:folder)
    └── [Ready for news articles - constraint issues to resolve]

## Component Details

### Hero Carousel (3 slides)
All use French i18n properties (language: "fr")

**Slide 1:**
- badge: "17 - 21 OCT. 2026"
- heading: "Le salon mondial de l'alimentation"
- body: "Paris Nord Villepinte"
- ctaLabel: "Découvrir"

**Slide 2:**
- badge: "SIAL Innovation 2026"
- heading: "Les innovations alimentaires de demain"
- body: "Découvrez les tendances qui façonnent le secteur"
- ctaLabel: "En savoir plus"

**Slide 3:**
- badge: "SIAL for Change"
- heading: "Un salon engagé pour une alimentation durable"
- body: "Retrouvez nos initiatives RSE et développement durable"
- ctaLabel: "Notre engagement"

### Key Figures (5 items)
**Created:**
- fig-1: 7 500 exposants
- fig-3: 400 000 produits
- fig-4: 200 000 visiteurs

**Failed due to unit property (non-i18n constraint):**
- fig-2: 200 pays (with unit)
- fig-5: 5 jours (with unit)

To fix: Recreate fig-2 and fig-5 without the unit property or check CND for non-i18n property declaration.

### Visitor Profiles (4 items)
- Distributeurs: GMS, hard discount, e-commerce, cash & carry, restauration collective
- Industriels: Fabricants, transformateurs, marques de distributeur
- Restaurateurs: CHR, gastronomie, restauration rapide, traiteurs
- Grand public: Journées grand public, animations, dégustations

### Trend Cards (3 items)
- **Durabilité:** Alimentation durable : les nouvelles protéines végétales
- **Santé:** Nutriscore et reformulation : où en est l'industrie ?
- **Tech:** Food tech : l'IA au service de la production alimentaire

### SIAL Network Events (7 items)
- SIAL Paris (Paris) - 17-21 octobre 2026
- SIAL Canada (Montréal / Toronto) - À venir
- SIAL China (Shanghai) - À venir
- SIAL India (New Delhi) - À venir
- SIAL Interfood (Jakarta) - À venir
- SIAL Middle East (Abu Dhabi) - À venir
- SIAL Network (International) - À venir

## Images Uploaded to DAM

### Logo (logo-header.jpg)
- **UUID:** f5c9f9bc-9909-40ef-af49-9873462de461
- **Path:** /sites/sial-paris/files/images/logo-header.jpg
- **Type:** jnt:file + jmix:image
- **Used in:** 
  - sialp:mainNavigation (logoImage property)
  - sialp:footer (sialLogo property)

### Video Thumbnail (video-thumbnail.jpg)
- **UUID:** 060d468c-52c5-4e8e-84f8-7dcf7f5de291
- **Path:** /sites/sial-paris/files/images/video-thumbnail.jpg
- **Type:** jnt:file + jmix:image
- **Used in:**
  - sialp:videoSection (thumbnailImage property)

## Known Issues & TODO

### 1. Key Figures - Unit Property
**Issue:** Properties fig-2 (200 pays) and fig-5 (5 jours) with unit failed to create.
**Cause:** Non-i18n `unit` property constraint mismatch.
**Fix:** Recreate these figures without unit or update CND unit property declaration.

```bash
# To recreate fig-2:
curl -s -u root:root \
  -H "Origin: http://localhost:8080" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8080/modules/graphql \
  -d '{
    "query":"mutation { jcr { addNode(parentPathOrId: \"/sites/sial-paris/home/main/key-figures\", name: \"fig-2\", primaryNodeType: \"sialp:keyFigure\", properties: [{name: \"number\", value: \"200\"}, {name: \"label\", value: \"pays\", language: \"fr\"}]) { uuid } } }"
  }'
```

### 2. News Articles - CND Constraints
**Issue:** Unable to create sialp:newsArticle nodes due to JCR folder structure constraints.
**Cause:** `jnt:folder` and `jnt:contentFolder` do not accept sialp:newsArticle as children directly.
**Fix Options:**
1. Check module CND for folder definitions that accept newsArticle
2. Create a custom news container type
3. Store news articles under different parent (e.g., directly under main page)

**Example articles to create when resolved:**
1. "SIAL Innovation 2026 : les candidatures sont ouvertes" (Innovation, 2026-03-15)
2. "Rapport tendances 2026 : les 5 grands enjeux de l'alimentaire" (Tendances, 2026-02-28)
3. "SIAL Paris 2026 : J-200, les inscriptions exposants progressent" (Événement, 2026-04-01)

### 3. Link Configuration
**TODO:** Add j:linkType properties to CTA components:
- mainNavigation: exposantCtaLabel, visiteurCtaLabel CTAs
- visitorProfile: Each profile's CTA
- trendsSection: Main CTA
- ctaDualCards: Left and right CTAs

### 4. Hero Slide Images
**TODO:** Add backgroundImage properties to hero slides (no images provided in migration)

## Publication Summary

✅ **All created content is PUBLISHED to live workspace**

- Home page and all children: PUBLISHED
- 6 Sub-pages: PUBLISHED
- Files/images folder: PUBLISHED
- Entire site visible to live visitors

## Access Points

**Live Site:**
- URL: http://localhost:8080/sites/sial-paris/home (when templates are finalized)

**Admin Interface:**
- Page Builder: http://localhost:8080/jahia/page-builder
- jContent (Editor): http://localhost:8080/jahia/jcontent
- GraphQL Playground: http://localhost:8080/modules/graphql

**Site Settings:**
- Key: sial-paris
- Languages: French (primary)
- Time Zone: Europe/Paris (default)
- Default Template: home (home page)

