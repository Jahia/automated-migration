# Migration Log — sial-paris

**Site:** https://www.sialparis.com/fr-FR
**Module:** sial-paris (namespace: sial)
**Started:** 2026-06-16

---

## [2026-06-16T14:05:00Z] Step 2 — Scaffold Module — COMPLETED

- **Tool:** npm init @jahia/module@latest sial-paris (Empty template set)
- **Output path:** projects/sial-paris/
- **Deps:** yarn install OK
- **Files created:** src/, settings/, docker/, package.json, vite.config.mjs, docker-compose.yml

---

## [2026-06-16T14:30:00Z] Step 1 — Analyze Website — COMPLETED

- **Method:** Chrome MCP (Cloudflare blocks curl/wget/WebFetch - HTTP 403 / JS challenge)
- **Tab ID:** 705482602 (still open with live site - cookie banner accepted)
- **Page captured:** Full home page text + accessibility tree (depth 4) + navigation tree (depth 6)
- **Components identified:** 21 types (14 parent types + 7 child types)
- **Page sections:** 13 sections top to bottom
- **Home page instances:** 14 component instances (+ ~70 children)
- **Templates needed:** home, basic, MainResource/default
- **Absolute areas:** header (sial:mainNavigation), footer (sial:footer)
- **Full-page types:** sial:newsArticle (jmix:mainResource)
- **Output files:**
  - analysis.md (component specs, section breakdown, navigation map)
  - component-manifest.json (21 types with field definitions)
  - content-data.json (actual FR content for all home page sections)
  - asset-inventory.json (images to capture + Chrome JS capture commands)
- **Gate result:** PASSED - all 4 files present, 14 instances captured

---

## [2026-06-16T12:34:00Z] Step 3 — Import Assets — COMPLETED
- **CSS:** 1 file (`static/css/sial-paris.css` — full design system, 350+ lines)
- **Images:** 2 files (logo-header.jpg 9.6KB, video-thumbnail.jpg 9.6KB)
- **Fonts:** 0 local files — Mukta loaded via Google Fonts @import in CSS
- **Notes:** Cloudflare blocked direct download of site CSS. Design tokens extracted via Chrome MCP (computed styles): font=Mukta, yellow=#FCE003, black=#000, button variants: solid-primary/primary/outline-white
- **Layout.tsx:** Wired with sial-paris.css via buildModuleFileUrl

## [2026-06-16T12:34:30Z] Step 4 — Templates — COMPLETED
- **Layout.tsx:** Updated with AbsoluteArea header (sial:mainNavigation) + footer (sial:footer), sial-paris.css AddResources
- **basic.server.tsx:** Updated with header/footer AbsoluteAreas + main Area
- **home.server.tsx:** Created with header/footer AbsoluteAreas + hero Area + main Area
- **Gate:** AbsoluteArea present in both templates ✓

## [2026-06-16T12:42:23Z] Step 5 — Components — COMPLETED
- **CND types:** 25 (21 types + 2 mixins)
- **Views:** 17 .server.tsx files
- **Build:** yarn build succeeded — dist/package.tgz ready
- **i18n:** EN + FR properties with ui.tooltip for every field
- **Fix applied:** AbsoluteArea parent prop added to basic + home templates

## [2026-06-16T12:48:24Z] Step 6 — Content — COMPLETED
- **Site key:** sial-paris
- **Nodes created:** 15 (hero carousel x3, key figures x5, video section, CTA dual cards, SIAL network, nav, footer, news articles x3)
- **Published:** FR workspace, all nodes
- **Live HTTP status:** 200
- **Script saved:** workflow-output/graphql-scripts/create-content.py
