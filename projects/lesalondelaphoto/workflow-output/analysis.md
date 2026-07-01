# Website Analysis: Le Salon de la Photo

**Reference URL:** https://www.lesalondelaphoto.com/fr-FR
**Date analyzed:** 2026-06-29
**Pages crawled:** 62
**Framework:** Sitecore SXA (server-rendered)
**Theme:** Comexposium Master1 Photo

---

## Site Structure

Le Salon de la Photo is an annual photography and video trade show in Paris organized by Comexposium. The site serves both visitors and exhibitors.

### Navigation Tree (3 levels)
```
Home (/fr-FR)
├── Le salon (/fr-FR/salon)
│   ├── Découvrez le Salon (/fr-FR/salon/a-propos)
│   ├── Qui expose ? (/fr-FR/salon/qui-expose)
│   ├── Qui visite ? (/fr-FR/salon/qui-visite)
│   ├── Le salon selon votre profil (/fr-FR/salon/profil-visiteur)
│   │   ├── Amateur averti
│   │   ├── Créateur de contenus
│   │   └── Professionnel
│   ├── Nos partenaires (/fr-FR/salon/partenaires)
│   └── Nos engagements RSE (/fr-FR/salon/rse)
├── Actualité photo (/fr-FR/actualite-photo)
│   ├── Actualité Photo (/fr-FR/actualite-photo/actualites)
│   ├── Conseils & Actualités (/fr-FR/actualite-photo/actus)
│   │   ├── [Article] Le Salon dévoile son visuel 2025
│   │   └── [Article] Comment retoucher des photos avec l'IA
│   └── Agenda photo (/fr-FR/actualite-photo/agenda-photo)
│       └── [Event] Lee Miller
├── Infos Pratiques (/fr-FR/infos-pratiques)
│   ├── Dates, Accès, Plan (/fr-FR/infos-pratiques/dates-acces-horaires)
│   ├── Photo Pass (/fr-FR/infos-pratiques/photo-pass)
│   ├── Transport & Hébergement (/fr-FR/infos-pratiques/comment-venir-au-salon)
│   ├── Liste des exposants (/fr-FR/infos-pratiques/catalogue)
│   └── FAQ Visiteur (/fr-FR/infos-pratiques/faq)
├── Animations et ateliers (/fr-FR/animations-ateliers)
│   ├── Les animations (/fr-FR/animations-ateliers/animations)
│   │   ├── Les Photos Spots
│   │   └── La Foire Internationale de Bièvres
│   ├── Les expositions photos (/fr-FR/animations-ateliers/expositions-photos)
│   │   ├── La Grande Expo
│   │   └── Les Zooms
│   ├── Le programme du salon
│   └── Les rencontres photo (/fr-FR/animations-ateliers/rencontres-photo)
│       └── Le forum des pros
├── Billetterie (/fr-FR/billetterie)
├── Exposants (/fr-FR/exposants)
└── Presse & Créateurs (/fr-FR/presse-createur-contenus)
```

---

## Component Identification

### Clustering Method
All HTML sections were extracted from 62 cached pages, grouped by **property shape** (the contributor-editable fields), ignoring CSS classes and markup. Sections with the same data shape are ONE type rendered by different views.

### Component Summary

| # | Component | NodeType | jmix:mainResource | Views | Frequency |
|---|-----------|----------|-------------------|-------|-----------|
| 1 | Hero | lsp:hero | no | heroBanner, card, compact | 20+ pages |
| 2 | EditorialBlock | lsp:editorialBlock | no | default, sectionTitle | 55+ pages |
| 3 | PromoBlock | lsp:promoBlock | no | default | 5 pages |
| 4 | PartnerItem | lsp:partnerItem | no | default | 2 pages |
| 5 | NewsArticle | lsp:newsArticle | yes | default, fullPage | 3+ pages |
| 6 | AgendaItem | lsp:agendaItem | yes | default, fullPage | 5+ pages |
| 7 | MainNav | lsp:mainNav | no | default | 62 pages (global) |
| 8 | Footer | lsp:footer | no | default | 62 pages (global) |
| 9 | JCRQuery | lsp:jcrQuery | no | default | mandatory |
| 10 | GridRow | lsp:gridRow | no | default | mandatory |
| 11 | HeroCarousel | lsp:heroCarousel | no (container) | default | 1 page (home) |
| 12 | PartnerCarousel | lsp:partnerCarousel | no (container) | default | 1 page (home) |
| 13 | CardGrid | lsp:cardGrid | no (container) | default | 3+ pages |
| 14 | ExternalEmbed | lsp:externalEmbed | no | default | 2 pages (exposants, billetterie) |
| 15 | TopBar | lsp:topBar | no (container) | default | 62 pages (global) |
| 16 | ContactBlock | lsp:contactBlock | no | default | 2 pages (contacts, home) |
| 17 | KeyFigures | lsp:keyFigures | no | default | 1 page (exposants) |
| 18 | Accordion | lsp:accordion | no (container) | default | 1 page (faq) |
| 19 | Tabs | lsp:tabs | no (container) | default | 2 pages (partenaires, photo-pass) |
| 20 | DateLieuHoraires | lsp:dateLieuHoraires | no | default | 1 page (dates-acces-horaires) |
| 21 | InfoCard | lsp:infoCard | no | default | 2 pages (boostez-visibilite, kit-media) |
| 22 | PageHeader | lsp:pageHeader | no | default | 60+ inner pages |
| 23 | ImageBlock | lsp:imageBlock | no | default | 6 pages (detail pages) |
| 24 | AnchorsLinks | lsp:anchorsLinks | no (container) | default | 1 page (boostez-visibilite) |
| 25 | SocialLink | lsp:socialLink | no | default | 62 pages (global, child of TopBar/Footer) |
| C1 | FooterLink | lsp:footerLink | no | default | 62 pages (global, child of Footer) |
| C2 | AccordionItem | lsp:accordionItem | no | default | 1 page (faq, child of Accordion) |
| C3 | CtaButton | lsp:ctaButton | no | default | 62 pages (global, child of TopBar/AnchorsLinks) |

> **C1-C3** are child component types declared as `childType` / `childTypes` on container components. They need their own CND definitions and views in the content-types step but are not standalone page-area components.

---

## Per-Component Detail

### 1. Hero (lsp:hero)
**Shape:** image + heading + subheading? + link?
**Area type:** page
**Views:**
- `heroBanner` (default): Full-width banner with background image, heading overlay, optional CTA button. Used as page hero on inner pages and carousel slides on home.
- `card`: Image card with overlay title and link. Used in picture-grid sections (Photos Spots, Grandes Rencontres, etc.).
- `compact`: Text-only card with title and link (used for quicklinks CTAs: "Acheter mon billet", etc.).
**Fields:**
- image: weakreference (picker[type='image']) — optional (hero image)
- heading: string (i18n, mandatory)
- subheading: string (i18n, optional) — used as description in card view
- link: j:linkType (linkTypeInitializer, optional)

### 2. EditorialBlock (lsp:editorialBlock)
**Shape:** heading + body? + image?
**Area type:** page
**Views:**
- `default`: Rich text block with optional heading and image. Used on 55+ inner pages for body content.
- `sectionTitle`: Just a heading (no body, no image). Used as visual section separators on home page.
**Fields:**
- heading: string (i18n, mandatory)
- body: string, richtext (i18n, optional)
- image: weakreference (picker[type='image'], optional)

### 3. PromoBlock (lsp:promoBlock)
**Shape:** heading + description? + videoLink? + link?
**Area type:** page
**Views:**
- `default`: Split layout with video embed on one side, text + CTA on the other. Used for "A vos marques, prêts, shootez!" section.
**Fields:**
- heading: string (i18n, mandatory)
- description: string (i18n, optional)
- videoLink: j:linkType (linkTypeInitializer, optional) — YouTube/Vimeo URL
- link: j:linkType (linkTypeInitializer, optional) — CTA button

### 4. PartnerItem (lsp:partnerItem)
**Shape:** logo + name + link?
**Area type:** page (child of partnerCarousel or placed standalone)
**Views:**
- `default`: Logo image with optional link. Used in partners carousel on home page and partners page.
**Fields:**
- logo: weakreference (picker[type='image'], mandatory)
- name: string (i18n, mandatory)
- link: j:linkType (linkTypeInitializer, optional)

### 5. NewsArticle (lsp:newsArticle)
**Shape:** title + image + publishDate? + summary? + body + tags + categories
**jmix:mainResource:** yes (has own URL, stored in content folder)
**Views:**
- `default`: Card/teaser shown in news listing grid. Image + title + date + summary.
- `fullPage`: Full article detail page. Hero image + title + date + body content + tags.
**Fields:**
- title: string (i18n, mandatory)
- image: weakreference (picker[type='image'], optional)
- publishDate: date (optional)
- summary: string (i18n, optional) — used in card view
- body: string, richtext (i18n, mandatory) — full article content
- tags: jmix:tagged (inherited)
- categories: weakreference, category[autoSelectParent=false] multiple (inherited from j:defaultCategory)

### 6. AgendaItem (lsp:agendaItem)
**Shape:** title + image + date? + location? + body + link?
**jmix:mainResource:** yes (has own URL, stored in content folder)
**Views:**
- `default`: Card/teaser shown in agenda listing. Image + title + date + location.
- `fullPage`: Full event detail page. Hero image + title + date + location + body + link.
**Fields:**
- title: string (i18n, mandatory)
- image: weakreference (picker[type='image'], optional)
- date: date (optional)
- location: string (i18n, optional)
- body: string, richtext (i18n, mandatory)
- link: j:linkType (linkTypeInitializer, optional) — external ticket/website link
- tags: jmix:tagged (inherited)

### 7. MainNav (lsp:mainNav)
**Shape:** Navigation menu (uses Jahia Navigation Menu component)
**Area type:** absolute (placed in header AbsoluteArea)
**Views:**
- `default`: 3-level dropdown navigation, logo + CTA buttons (billetterie, exposants)
**Fields:** None — uses JCR navigation API (`getChildNodes` on home)

### 8. Footer (lsp:footer)
**Shape:** Footer with links and legal info
**Area type:** absolute (placed in footer AbsoluteArea)
**Views:**
- `default`: Multi-column footer with navigation links, legal links, social icons
**Fields:**
- footerText: string, richtext (i18n, optional)
- links: child nodes of type lsp:footerLink

### 9. JCRQuery (lsp:jcrQuery)
Mandatory per AGENTS rule #16. Generic listing component.
**Views:**
- `default`: Configurable listing with type selector, sort, filter, pagination.

### 10. GridRow (lsp:gridRow)
Mandatory per AGENTS rule #16. Layout component for JCRQuery results.
**Views:**
- `default`: Responsive grid layout for cards.

### 11. HeroCarousel (lsp:heroCarousel)
**Container:** yes (isContainer: true, childType: lsp:hero)
**Views:**
- `default`: Bootstrap carousel that renders children (lsp:hero) as slides.
**Fields:**
- autoplay: boolean (optional)
- interval: string (optional, default "5000")

### 12. PartnerCarousel (lsp:partnerCarousel)
**Container:** yes (isContainer: true, childType: lsp:partnerItem)
**Views:**
- `default`: Swiffy slider carousel rendering partner logos.
**Fields:**
- title: string (i18n, optional) — e.g. "Nos partenaires"

### 13. CardGrid (lsp:cardGrid)
**Container:** yes (isContainer: true, childType: lsp:hero)
**Views:**
- `default`: Responsive grid layout rendering cards (lsp:hero in `card` view).
**Fields:**
- title: string (i18n, optional) — section title above grid
- columns: string, choicelist '2','3','4' = '3' (layout property for contributor)

### 14. ExternalEmbed (lsp:externalEmbed)
**Shape:** j:linkType + embedTitle? + embedHeight?
**Area type:** page
**Views:**
- `default`: Sandboxed, titled `<iframe>` embedding an external platform (event.lesalondelaphoto.com). Used for the exposants exhibitor list and the billetterie ticketing page.
**Fields:**
- j:linkType: string, choicelist[linkTypeInitializer] (mandatory, defaultValue: external) — Jahia injects j:url with the embed target
- embedTitle: string (i18n, mandatory) — accessible iframe title
- embedHeight: long (optional, default: 800) — iframe height in px

### 15. TopBar (lsp:topBar)
**Shape:** hashtag? + socialLink* + ctaButton*  
**Area type:** page (absolute — placed in header above MainNav)  
**Container:** yes (isContainer: true, childType: lsp:socialLink + lsp:ctaButton)  
**SXA source:** top-bar, top-navbar
**Views:**
- `default`: Top utility strip with social links, CTA buttons (Devenir exposant, Espace exposant), and optional hashtag text.
**Fields:**
- hashtag: string (i18n, optional) — e.g. "#SalonPhotoetVideo"
- socialLinks: child nodes of type lsp:socialLink
- ctaButtons: child nodes of type lsp:ctaButton

### 16. ContactBlock (lsp:contactBlock)
**Shape:** prenomNom + fonction + email + telephone + lienBlog
**Area type:** page  
**SXA source:** contact-block
**Views:**
- `default`: Contact info card with name, role, email, phone, and blog link.
**Fields:**
- prenomNom: string (i18n, mandatory)
- fonction: string (i18n, optional)
- email: string (i18n, optional)
- telephone: string (i18n, optional)
- lienBlog: j:linkType (linkTypeInitializer, optional)

### 17. KeyFigures (lsp:keyFigures)
**Shape:** chiffre*4 + description*4
**Area type:** page  
**SXA source:** key-figures, animated-key-figures
**Views:**
- `default`: Stat band with 4 key figures (number + description each).
**Fields:**
- chiffre1: string (i18n, mandatory)
- description1: string (i18n, mandatory)
- chiffre2: string (i18n, mandatory)
- description2: string (i18n, mandatory)
- chiffre3: string (i18n, mandatory)
- description3: string (i18n, mandatory)
- chiffre4: string (i18n, mandatory)
- description4: string (i18n, mandatory)

### 18. Accordion (lsp:accordion)
**Shape:** container of accordionItem
**Area type:** page  
**Container:** yes (isContainer: true, childType: lsp:accordionItem)  
**SXA source:** accordion
**Views:**
- `default`: Accordion container of collapsible FAQ items.
**Fields:**
- heading: string (i18n, optional) — accordion group title

### 19. Tabs (lsp:tabs)
**Shape:** container of editorialBlock (tab panels)
**Area type:** page  
**Container:** yes (isContainer: true, childType: lsp:editorialBlock)  
**SXA source:** tabs
**Views:**
- `default`: Tabbed container of content panels (each panel is a rich-text block).
**Fields:** None (layout component; children are the content)

### 20. DateLieuHoraires (lsp:dateLieuHoraires)
**Shape:** titre*3 + description*3
**Area type:** page  
**SXA source:** date-lieu-horaires
**Views:**
- `default`: Practical info block with 3 icon-cards for Dates, Lieu, Horaires.
**Fields:**
- titre1: string (i18n, mandatory)
- description1: string, richtext (i18n, mandatory)
- titre2: string (i18n, mandatory)
- description2: string, richtext (i18n, mandatory)
- titre3: string (i18n, mandatory)
- description3: string, richtext (i18n, mandatory)

### 21. InfoCard (lsp:infoCard)
**Shape:** icone + titre + description
**Area type:** page  
**SXA source:** item-content-popin-picture
**Views:**
- `default`: Icon + title + description card with optional image popup.
**Fields:**
- icon: weakreference (picker[type='image'], optional) — icon image
- titre: string (i18n, mandatory)
- description: string, richtext (i18n, optional)
- iconeDescription: string (i18n, optional) — alt text for icon

### 22. PageHeader (lsp:pageHeader)
**Shape:** titre + sousTitre? + arriereTitre? + datePublication?
**Area type:** page  
**SXA source:** title (banner-title* variants, small-banner)
**Views:**
- `default`: Page/article title banner with title, subtitle, eyebrow (arrière-titre), and optional publication date.
**Fields:**
- titre: string (i18n, mandatory)
- sousTitre: string (i18n, optional)
- arriereTitre: string (i18n, optional) — eyebrow/super-title above the main title
- datePublication: date (optional) — displayed on news articles

### 23. ImageBlock (lsp:imageBlock)
**Shape:** image + caption?
**Area type:** page  
**SXA source:** image, container-bp (image wrapper)
**Views:**
- `default`: Standalone image with optional caption.
**Fields:**
- image: weakreference (picker[type='image'], mandatory)
- imagecaption: string (i18n, optional)

### 24. AnchorsLinks (lsp:anchorsLinks)
**Shape:** container of ctaButton (in-page jump links)
**Area type:** page  
**Container:** yes (isContainer: true, childType: lsp:ctaButton)  
**SXA source:** anchors-links
**Views:**
- `default`: Horizontal bar of in-page anchor/jump links.
**Fields:** None (children: lsp:ctaButton with anchor URLs)

### 25. SocialLink (lsp:socialLink)
**Shape:** platform + j:linkType
**Area type:** page (child of TopBar or Footer)  
**Views:**
- `default`: Single social-media icon link (FA brand icon for instagram/facebook/linkedin/x/youtube).
**Fields:**
- platform: string, choicelist (mandatory) — instagram | facebook | linkedin | x | youtube
- j:linkType: string, choicelist[linkTypeInitializer] (mandatory, defaultValue: external)

### 26. FooterLink (lsp:footerLink)
**Shape:** label + j:linkType
**Area type:** page (child of Footer)  
**Views:**
- `default`: Single footer link with label and URL.
**Fields:**
- label: string (i18n, mandatory)
- j:linkType: string, choicelist[linkTypeInitializer] (mandatory)

### 27. AccordionItem (lsp:accordionItem)
**Shape:** title + body
**Area type:** page (child of Accordion)  
**Views:**
- `default`: Single accordion item with a question title and expandable rich-text answer.
**Fields:**
- title: string (i18n, mandatory)
- body: string, richtext (i18n, mandatory)

### 28. CtaButton (lsp:ctaButton)
**Shape:** label + j:linkType
**Area type:** page (child of TopBar or AnchorsLinks)  
**Views:**
- `default`: Simple call-to-action button with label and link.
**Fields:**
- label: string (i18n, mandatory)
- j:linkType: string, choicelist[linkTypeInitializer] (mandatory)

---

## SXA Coverage
**SXA component types extracted:** 42  
**Mapped to Jahia types:** 32 (see sxaSource arrays in component-manifest.json)  
**Deliberately ignored:** 10 (link, plain-html, breadcrumb, snippet, previous-next, image-de-fond, facet-dropdown, facet-aggregated, facet-summary, load-more)  
**Reason for ignored:** structural wrappers, search facets (no Jahia backend), or modelled as properties/linkTypeInitializer on hosting components.

## Field Split Decisions
- **title SXA component** → split into: `lsp:pageHeader` (when marking a page/article heading banner) and `lsp:editorialBlock` sectionTitle view (when used as a visual section separator). Rationale: different contributor intent; sectionTitle is a view on the general richtext container.
- **container SXA** → `lsp:gridRow` (layout only) + `lsp:cardGrid` (when containing hero cards). Rationale: gridRow is the mandatory layout component; cardGrid is the picture-grid container.
- **link SXA** → modelled as `j:linkType` on the parent component (never a standalone type — AGENTS rule #14).
- **plain-html** → raw HTML like hamburger menus and iframe wrappers that belong in the theme/layout, not as editable content.
- **breadcrumb** → rendered by the page template from JCR tree, no content type needed.
- **snippet / previous-next** → page-template-level navigation, no content type.
- **image-de-fond** → background-image property on the parent component (e.g. hero background), not a standalone type.
- **facet-* + load-more** → no Jahia backend equivalent; replaced by JCRQuery with jmix:tagged/category filtering + loadMore property.
