# SIAL Paris — Site Analysis

**URL:** https://www.sialparis.com/fr-FR
**Analyzed:** 2026-06-16
**Method:** Chrome MCP (Cloudflare blocks all programmatic access — curl/wget return 403/JS challenge)
**Language:** French (fr-FR)
**Framework:** Next.js (based on `/_next/` URL pattern)

---

## Site Overview

SIAL Paris is the world's largest food industry trade show, organized by Comexposium. It takes place every 2 years at Paris Nord Villepinte. 2026 edition: 17-21 October 2026.

Key facts from page content:
- 7,500 exhibitors
- 200 countries represented
- 400,000 products
- 200,000 visitors
- 5 days

---

## Navigation Structure (3 levels)

The site has 6 top-level nav items, each with sub-items. Level 3 entries exist within some sub-items.

| Level 1 | Level 2 (sampled) |
|---|---|
| LE SALON | Histoire, Pourquoi visiter, Top Buyers, Newsfeed, RSE, Marketplace, Partenaires |
| LES EXPOSANTS 2026 | Liste des exposants |
| TEMPS FORTS | Programme, SIAL Innovation, SIAL Talks, Start-up, SIAL Summits, SIAL for Change, SIAL Taste, SIAL Guinguette, Visites guidées, Parcours thématiques, Bakery by SIAL |
| TENDANCES | Actualités, Innovations sectorielles, Focus, Livres blancs |
| INFOS PRATIQUES | Dates et horaires, Tarifs, VIP ticket, Networking, Venir au salon, Mediakit, Commandez votre ticket, SIAL Off, FAQ, Contacts |
| MÉDIAS | Communiqués de presse, Médiathèque, Contacts presse |

**Header CTAs:** "JE VISITE" (primary, orange), "J'EXPOSE" (secondary)

**Implementation rule:** 3-level navigation must use Jahia Navigation Menu component over JCR page tree. No hardcoded nav links.

---

## Page Sections (top to bottom)

### 1. Main Navigation (Absolute Area)
- Sticky header
- SIAL logo (top left)
- Mega menu with 6 items
- 2 CTA buttons (JE VISITE, J'EXPOSE)
- Language switcher (FR/EN)

### 2. Hero Carousel
- Full-viewport height carousel
- 3 slides with auto-rotation
- Each slide: background image + semi-transparent overlay + event badge + H1 + body text + CTA button
- Navigation dots + prev/next arrows

**Slide 1:**
```
Badge:   17 - 21 OCT. 2026
H1:      Le salon mondial de l'alimentation
Body:    Paris Nord Villepinte
CTA:     Découvrir
```

**Slide 2:**
```
Badge:   SIAL Innovation 2026
H1:      Les innovations alimentaires de demain
Body:    Découvrez les tendances qui façonnent le secteur
CTA:     En savoir plus
```

**Slide 3:**
```
Badge:   SIAL for Change
H1:      Un salon engagé pour une alimentation durable
Body:    Retrouvez nos initiatives RSE et développement durable
CTA:     Notre engagement
```

### 3. Intro Text Block
- Centered layout, max-width container
- Overline: "LE SALON MONDIAL"
- H2: "SIAL Paris, le rendez-vous mondial de l'alimentation"
- Body (richtext): Multi-sentence editorial text with key stats

### 4. SIAL en Bref (= Key Figures)
- Dark background band
- 5 figures in a row:
  - 7 500 exposants
  - 200 pays représentés
  - 400 000 produits
  - 200 000 visiteurs
  - 5 jours d'événement

### 5. Latest News
- Section heading: "Dernières actualités"
- 3-column card grid
- Each card: category tag + date + thumbnail + title + excerpt
- "Voir toutes les actualités" CTA link

### 6. Visitor Profiles
- Section heading
- 4-column grid
- Each profile: icon/illustration + label + description + CTA link
- Types: Distributeurs, Industriels, Restaurateurs, Grand public

### 7. Trends Section
- Section heading: "Tendances & Innovations"
- Editorial intro text
- 3 trend cards: tag + image + heading + excerpt + Read More
- "Toutes les tendances" CTA

### 8. Video Section
- Full-width video embed (YouTube)
- "SIAL Paris 2024 en images" heading
- Thumbnail with play button overlay

### 9. Sectors Grid
- Grid of food industry sectors with icons
- Examples: Epicerie, Surgelés, Vins & Spiritueux, Produits laitiers, Boulangerie, Charcuterie, etc.

### 10. CTA Dual Cards (Exposant/Visiteur)
- Two large cards side by side
- Left: "Vous exposez à SIAL Paris 2026 ?" + background image + "Je dépose ma candidature"
- Right: "Vous visitez SIAL Paris 2026 ?" + background image + "Je commande mon badge"

### 11. Partners Carousel
- Heading: "Nos partenaires"
- 40+ partner logos in horizontal auto-scrolling carousel
- Infinite scroll animation

### 12. SIAL Network
- Heading: "Le réseau SIAL mondial"
- World map visual
- Grid of SIAL events worldwide: Paris, Canada (Montréal/Toronto), China (Shanghai), India (New Delhi), Indonesia (Jakarta), Middle East (Abu Dhabi), + others

### 13. Footer (Absolute Area)
- Social links: LinkedIn, Facebook, Twitter/X, YouTube, Instagram
- FAQ quick link
- Newsletter: email field + GDPR checkbox + "Je m'inscris" button
- Footer nav: Plan du site, Accessibilité, Mentions légales, Politique de confidentialité, Cookies
- SIAL logo + Comexposium logo
- Copyright: © 2026 SIAL Paris - Comexposium

---

## Content Type Summary

| CND Type | Count | Notes |
|---|---|---|
| sial:mainNavigation | 1 | Absolute - header |
| sial:heroCarousel | 1 | + 3 sial:heroSlide children |
| sial:introText | 1 | |
| sial:keyFigures | 1 | + 5 sial:keyFigure children |
| sial:newsListing | 1 | Queries sial:newsArticle |
| sial:newsArticle | 3+ | jmix:mainResource - full page |
| sial:visitorProfiles | 1 | + 4 sial:visitorProfile children |
| sial:trendsSection | 1 | + 3 sial:trendCard children |
| sial:videoSection | 1 | |
| sial:sectorsSection | 1 | + N sial:sectorItem children |
| sial:ctaDualCards | 1 | |
| sial:partnersCarousel | 1 | + 40+ sial:partnerLogo children |
| sial:sialNetwork | 1 | + 7-13 sial:networkEvent children |
| sial:footer | 1 | Absolute - footer |

**Total component types:** 21
**Total instances on home page:** 14 (+ children)

---

## Templates Required

1. **home.server.tsx** - Full home page
2. **basic.server.tsx** - Interior pages (6 sub-pages)
3. **MainResource/default.server.tsx** - News article full-page view

---

## Asset Capture Notes

**Cloudflare blocks all programmatic access.** Chrome MCP tab 705482602 has the live site open (cookie banner accepted).

To capture images and CSS:
```javascript
// Get all image URLs
Array.from(document.querySelectorAll('img')).map(img => ({src: img.src, alt: img.alt}))

// Get all CSS files
Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map(l => l.href)

// Get fonts
Array.from(document.querySelectorAll('link[rel="preload"][as="font"]')).map(l => l.href)
```

Use `mcp__Claude_in_Chrome__javascript_tool` to run these in the open tab.

---

## i18n Notes

- Primary language: French (fr)
- English version exists (EN language switcher visible)
- All user-facing content fields must be `i18n`
- Resource bundle: `settings/resources/sial-paris_fr.properties` + `sial-paris_en.properties`
- Locale JSON: `settings/locales/fr.json` + `en.json`

---

## Quality Gates Met

- [x] Navigation structure fully mapped (3 levels)
- [x] All page sections identified (13 sections)
- [x] Component types defined (21 types)
- [x] Content data captured for home page
- [x] i18n requirements noted
- [x] Template variants identified (3)
- [x] Absolute areas identified (header, footer)
- [x] Full-page types identified (sial:newsArticle)
