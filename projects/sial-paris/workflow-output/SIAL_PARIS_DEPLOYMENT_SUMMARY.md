# SIAL Paris Site - Deployment Summary

## Site Created Successfully

**Site Key:** `sial-paris`  
**Site Display Name:** SIAL Paris  
**Primary Language:** French (fr)  
**Template Set:** sial-paris  
**Status:** Published to Live Workspace

## Site Structure

### Home Page (`/sites/sial-paris/home`)

#### Header Area (AbsoluteArea)
- **Navigation Component** (`sialp:mainNavigation`)
  - Exposant CTA Label: "Je suis exposant"
  - Visiteur CTA Label: "Je suis visiteur"
  - Logo: SIAL logo (uploaded to DAM)

#### Footer Area (AbsoluteArea)
- **Footer Component** (`sialp:footer`)
  - Newsletter Heading: "Restez informé"
  - Newsletter Placeholder: "Votre adresse email"
  - Copyright Text: "© 2026 SIAL Paris - Comexposium"
  - Logo: SIAL logo (uploaded to DAM)

#### Hero Section (`hero` area)
- **Hero Carousel** (`sialp:heroCarousel`) with 3 slides:
  1. Badge: "17 - 21 OCT. 2026" | Heading: "Le salon mondial de l'alimentation"
  2. Badge: "SIAL Innovation 2026" | Heading: "Les innovations alimentaires de demain"
  3. Badge: "SIAL for Change" | Heading: "Un salon engagé pour une alimentation durable"

#### Main Content Area (`main` area)
1. **Intro Text** (`sialp:introText`)
   - Overline: "LE SALON MONDIAL"
   - Heading: "SIAL Paris, le rendez-vous mondial de l'alimentation"
   - Body: Full description text

2. **Key Figures** (`sialp:keyFigures`) - 5 figures:
   - 7,500 exposants
   - 200 countries represented
   - 400,000 products
   - 200,000 visitors
   - 5 days of events

3. **News Listing** (`sialp:newsListing`)
   - Heading: "Dernières actualités"
   - Max Items: 3
   - CTA Label: "Voir toutes les actualités"

4. **Visitor Profiles** (`sialp:visitorProfiles`)
   - 4 profiles: Distributeurs, Industriels, Restaurateurs, Grand public
   - Each with description and "En savoir plus" CTA

5. **Trends Section** (`sialp:trendsSection`)
   - Heading: "Tendances & Innovations"
   - 3 trend cards: Durabilité, Santé, Tech
   - CTA Label: "Toutes les tendances"

6. **Video Section** (`sialp:videoSection`)
   - Heading: "SIAL Paris 2024 en images"
   - Video URL: https://www.youtube.com/embed/sparis2024
   - Thumbnail: Video thumbnail image (uploaded)

7. **CTA Dual Cards** (`sialp:ctaDualCards`)
   - Left: "Vous exposez à SIAL Paris 2026 ?" / "Je dépose ma candidature"
   - Right: "Vous visitez SIAL Paris 2026 ?" / "Je commande mon badge"

8. **SIAL Network** (`sialp:sialNetwork`)
   - 7 network events:
     - SIAL Paris (Paris)
     - SIAL Canada (Montréal / Toronto)
     - SIAL China (Shanghai)
     - SIAL India (New Delhi)
     - SIAL Interfood (Jakarta)
     - SIAL Middle East (Abu Dhabi)
     - SIAL Network (International)

### Sub-Pages (all with basic template)
- `/sites/sial-paris/home/le-salon` - Le Salon
- `/sites/sial-paris/home/les-exposants` - Les Exposants
- `/sites/sial-paris/home/temps-forts` - Temps Forts
- `/sites/sial-paris/home/tendances` - Tendances
- `/sites/sial-paris/home/infos-pratiques` - Infos Pratiques
- `/sites/sial-paris/home/medias` - Médias

Each sub-page has a `main` content area ready for additional content.

### Digital Assets (`/sites/sial-paris/files/images/`)
- `logo-header.jpg` - SIAL logo (UUID: f5c9f9bc-9909-40ef-af49-9873462de461)
- `video-thumbnail.jpg` - Video thumbnail (UUID: 060d468c-52c5-4e8e-84f8-7dcf7f5de291)

## Publication Status

✅ **All content published to live workspace**
- Home page and all child components
- Sub-pages (6 pages)
- Digital assets (2 images)

## Next Steps

### News Articles
The news article structure was designed but requires additional CND constraints to be resolved. To create news articles in the future:
1. Create `/sites/sial-paris/actualites/` folder
2. Add `sialp:newsArticle` nodes with:
   - title, category, publishDate, excerpt, body (all in French)
   - Publish to live workspace

Example articles to create:
1. "SIAL Innovation 2026 : les candidatures sont ouvertes" (Innovation, 2026-03-15)
2. "Rapport tendances 2026 : les 5 grands enjeux de l'alimentaire" (Tendances, 2026-02-28)
3. "SIAL Paris 2026 : J-200, les inscriptions exposants progressent" (Événement, 2026-04-01)

### Content Population
- Add link targets (`j:linkType` with `j:linknode`) on CTAs
- Populate news listing component with query to fetch articles
- Add images to hero slides and other components where applicable

### Workflow Scripts
All GraphQL scripts saved to: `/Users/stephane/Runtimes/0.Modules/jahiaMigration/projects/sial-paris/workflow-output/graphql-scripts/`

- `01-create-page-areas.sh` - Create areas
- `02-create-header-footer.sh` - Create header and footer
- `03-create-hero-carousel.sh` - Create hero slides
- `04-create-main-content.sh` - Create intro, figures, listings, profiles
- `05-create-trends-video-cta-network.sh` - Create trends, video, CTAs, network
- `06-create-sub-pages.sh` - Create sub-pages
- `08-publish-all.sh` - Publish content

### Image UUID Mapping
Saved to: `/tmp/sial-paris-images.json`

```json
{
  "logo-header.jpg": "f5c9f9bc-9909-40ef-af49-9873462de461",
  "video-thumbnail.jpg": "060d468c-52c5-4e8e-84f8-7dcf7f5de291"
}
```

## Live Site Access

Once the module templates are finalized, the site will be accessible at:
- **Live Site:** http://localhost:8080/sites/sial-paris
- **Page Builder:** http://localhost:8080/jahia/page-builder
- **jContent:** http://localhost:8080/jahia/jcontent (Editor interface)

