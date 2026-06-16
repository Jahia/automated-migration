---
description: Analyze a website to identify all Jahia components needed for migration
---

> See full skill guide at `.agents/skills/01-analyze-website/SKILL.md`

## State management (run at start and end)

**At the START of this step:**
```bash
# Locate PROJECT_DIR (find definitions.cnd or package.json with jahia key)
# Create workflow-output/ if absent
mkdir -p "$PROJECT_DIR/workflow-output"

# Update state.json — mark step in_progress
# If state.json doesn't exist yet, create it with siteUrl and startedAt
# Set: steps["1-analyze"].status = "in_progress"
```

**At the END of this step (before presenting results to user):**
```bash
# 1. Verify all 4 output files exist
ls "$PROJECT_DIR/workflow-output/"{analysis.md,component-manifest.json,content-data.json,asset-inventory.json}

# 2. Count instances
INSTANCE_COUNT=$(jq '.componentInstances | length' "$PROJECT_DIR/workflow-output/content-data.json")
CHILD_COUNT=$(jq '[.componentInstances[].children // [] | length] | add // 0' "$PROJECT_DIR/workflow-output/content-data.json")

# 3. Update state.json
# Set: steps["1-analyze"].status = "completed"
# Set: steps["1-analyze"].notes = "N components, $INSTANCE_COUNT instances, $CHILD_COUNT children"
# Set: steps["1-analyze"].completedAt = <ISO timestamp>

# 4. Append to migration-log.md
cat >> "$PROJECT_DIR/workflow-output/migration-log.md" << EOF
## [$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Step 1 — Analyze Website — COMPLETED
- **Outputs:** analysis.md, component-manifest.json ($INSTANCE_COUNT instances, $CHILD_COUNT children), content-data.json, asset-inventory.json
- **Gate result:** $([ $INSTANCE_COUNT -ge 5 ] && echo "PASS" || echo "WARN — only $INSTANCE_COUNT instances, may be incomplete")
EOF
```

### Reference screenshots (MANDATORY — taken during analysis)

After identifying all sections, take a full-page screenshot of the original site at **1440px width** using Chrome MCP. Save it as the visual reference for the final comparison gate.

```
workflow-output/screenshots/
  reference-home-1440.png     ← full page at desktop width
  reference-home-375.png      ← full page at mobile width
  reference-<section>.png     ← one crop per identified section (for per-component comparison)
```

**How to capture:**
1. Open the source URL in Chrome (use Chrome MCP `navigate` + `computer screenshot`)
2. Resize to 1440px width, scroll to top, take full-page screenshot → save as `reference-home-1440.png`
3. Resize to 375px, screenshot → `reference-home-375.png`
4. For each identified section: scroll to it, crop screenshot → `reference-<sectionSlug>.png`

Record screenshot paths in `state.json`:
```bash
jq '.referenceScreenshots = {"home1440": "workflow-output/screenshots/reference-home-1440.png", "home375": "workflow-output/screenshots/reference-home-375.png"}' "$STATE" > /tmp/state.tmp && mv /tmp/state.tmp "$STATE"
```

These screenshots are the ground truth for Gate 4 (visual comparison). Without them, visual fidelity cannot be verified.

If any output file is missing: set `1-analyze.status = "failed"` in state.json, append FAILED entry to migration-log.md, and stop.

---

Analyze the provided website and identify all components that need to be implemented in Jahia.

The user will provide either:
- A website URL to analyze
- A screenshot of a webpage
- HTML/CSS code
- A path to an HTML file

## Instructions

### Step 1: Obtain HTML Content

**If given a URL:**
- First, try to fetch the page using WebFetch
- If WebFetch fails (403, 503, or other access errors), automatically download the entire website using wget with all assets:
  ```bash
  # Create download directory for reuse by /import-website-assets
  mkdir -p /tmp/website-download

  # Download website with all assets
  wget --recursive \
       --level=2 \
       --no-parent \
       --convert-links \
       --adjust-extension \
       --page-requisites \
       --no-clobber \
       --user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
       --directory-prefix=/tmp/website-download \
       "{URL}"

  # Find the main HTML file for analysis
  find /tmp/website-download -name "index.html" -o -name "*.html" | head -1 > /tmp/webpage-analysis.html
  ```
- Then proceed to Step 2

**Note:** The website will be downloaded to `/tmp/website-download/` for reuse by `/import-website-assets` command

**If given a file path:**
- Read the HTML content directly
- Proceed to Step 2

### Step 2: Prepare HTML for Analysis

Save the **raw HTML** (no attribute conversion) to `/tmp/webpage.html` for section analysis.

**Do NOT convert `class` → `className` or modify any attributes at this stage.** The HTML fragment extracted in Step 5 must remain raw HTML so the component-implementer can do the mechanical JSX conversion itself. Pre-converting here causes `data-*` attributes and other non-standard attributes to be lost or altered.

### Step 3: Identify High-Level Sections

**Priority order for section detection:**

1. **`<section>` tags** - Primary markers for distinct sections
2. **`<article>` tags** - Content article sections
3. **Semantic HTML5 tags**: `<header>`, `<footer>`, `<nav>`, `<aside>`, `<main>`
4. **`<div>` with semantic classes** matching patterns:
   - Layout: `hero`, `banner`, `wrapper`, `container`, `section`
   - Navigation: `header`, `navigation`, `nav`, `menu`
   - Content: `content`, `main`, `body`, `article`
   - Footer: `footer`, `bottom`, `site-footer`
   - Components: `*-section`, `*-block`, `*-area`, `*-zone`
5. **`<div>` with ARIA role attributes**: `role="banner"`, `role="navigation"`, etc.

### Step 4: Analyze Each Section

For each identified section:

**A. Determine Component Type:**
- **Full Section Component**: Entire section (Hero, Navigation, Footer, Feature Grid)
- **Composite Component**: Section with repeated sub-elements (Card Grid, List)
- **Simple Component**: Single purpose (Button, Link, Image)

**B. Extract Structure:**
- Main content elements (headings, text, images, links)
- Repeating patterns (identify potential sub-components)
- Interactive elements (forms, buttons, accordions)
- Layout structure (grid, flex, columns)

**C. Determine Implementation:**
- **Server-only**: Static content, no interactivity
- **Client-interactive**: Forms, toggles, animations, state management
- **Hybrid**: Server-rendered with client hydration

### Step 4b: Extract Carousel/Slider Configuration

For any section that contains a carousel, slider, or repeating-item wrapper:

1. **Capture the wrapper element's configuration attributes verbatim:**
   - `id` (the exact ID from the source, not an invented descriptive name)
   - All `data-*` configuration attributes (e.g., `data-padding`, `data-show-dekstop`, `data-show-tab`, `data-show-mobile`, `data-items`, `data-margin`, `data-autoplay`, `data-loop`, etc.)
   - Any wrapper CSS classes (e.g., `owl-carousel`, `owl-mobile-fitwidth`, `swiper-container`)

2. **Record the configuration as a `carouselConfig` object** in the component spec:
   ```json
   "carouselConfig": {
     "id": "js-owl-carousel0",
     "wrapperClasses": "owl-carousel owl-theme owl-mobile-fitwidth owl-card-box",
     "dataAttributes": {
       "data-padding": "0",
       "data-show-dekstop": "4",
       "data-show-tab": "2",
       "data-show-mobile": "1"
     }
   }
   ```

3. **Use the original `id` attribute** — do NOT invent descriptive names (e.g., keep `js-owl-custom-section-0`, not `js-owl-whats-new`). The carousel JavaScript library uses these IDs and renaming them breaks prev/next navigation.

### Step 5: Create Component Specification

For each HIGH-LEVEL component, document:

**Component Identity:**
- Name (e.g., `HeroSection`, `NavigationMenu`, `ContentGrid`)
- Description (purpose and visual characteristics)
- Location in page (header, main, footer)

**Content Structure:**
- Required fields (title, description, image, etc.)
- Optional fields
- Repeating children (for grids, lists)

**Image field rule:** Any field whose source value is an image URL (from `src`, `data-bg`, `data-src`, `srcset`, `background-image`) must be typed as `weakreference, picker[type='image']` with constraint `< jmix:image` in the component spec — NOT as `string`. The actual CDN/external URL goes into `content-data.json` for the `/create-content` step, but the CND type must be `weakreference` to enable Jahia's DAM image picker for content editors.

**HTML Fragment (CRITICAL — MUST be extracted from source file, NEVER written from memory):**

Follow this exact procedure to extract each component's HTML fragment:

1. **Read the saved HTML file** (`/tmp/webpage.html`) and locate the component's root element using its identifying CSS class or HTML tag (e.g., `header-wrapper`, `home-banner-explore`, the `<section>` containing a specific carousel `id`)

2. **Copy the COMPLETE HTML block** from the opening tag to the closing tag — every element, every attribute, every nested tag. Do NOT simplify, summarize, or rewrite any part of it.

3. **For container components (carousels, grids):** Copy the full wrapper structure INCLUDING one representative child item. The child item must be complete with every attribute.

4. **Replace ONLY dynamic text content** with `{placeholders}`:
   - Text inside tags: `<h1>Actual Heading</h1>` → `<h1>{heading}</h1>`
   - Image URLs in attributes: `data-bg="https://cdn.example.com/photo.jpg"` → `data-bg="{backgroundImage}"`
   - Link hrefs: `href="/us/en/restaurants"` → `href="{href}"`

5. **NEVER modify, remove, or simplify any of these:**
   - CSS classes (keep ALL classes exactly as they appear)
   - `data-*` attributes (keep ALL of them, even ones that seem unused)
   - `aria-*` and `role` attributes
   - Wrapper `<div>` elements (keep every nesting level)
   - `<noscript>` blocks
   - `<source>` elements inside `<picture>` tags
   - `<form>` elements with all their attributes
   - Inline `style` attributes

6. **Verification:** After extracting, count the total HTML elements and attributes in your fragment. Compare against the source. If your fragment is significantly shorter, you likely simplified something — go back and extract again.

**Why this matters:** The component-implementer agent will convert this fragment to JSX mechanically. If the fragment is wrong, the implemented component will be wrong, and the page won't render correctly. There is no recovery step — a simplified fragment produces a broken component.

**Technical Details:**
- Server-only or needs client component
- Sub-components needed (Card, Button, Link)
- Special considerations (responsive, animations)

### Step 6: Extract Content Data

**CRITICAL: Extract actual content from the website to enable accurate recreation.**

For each component instance found on the page, extract the actual content values:

**A. Create content extraction map:**

For each component instance:
1. **Identify component type** (HeroSection, ContentTile, BannerSection, etc.)
2. **Extract all field values** from the HTML:
   - Text content (headings, body text, labels)
   - Links (href attributes, CTA URLs)
   - Image URLs (src attributes)
   - CSS classes and styling properties
   - Any other dynamic content

**B. Structure the data:**

```json
{
  "pageMetadata": {
    "title": "Page Title from <title> tag",
    "url": "https://example.com",
    "description": "Meta description",
    "language": "en"
  },
  "componentInstances": [
    {
      "componentType": "HeroSection",
      "instanceName": "hero",
      "order": 1,
      "contentArea": "main",
      "fields": {
        "heading": "Actual heading text extracted",
        "bodyText": "<p>Actual HTML body text</p>",
        "ctaText": "Button text",
        "ctaLink": "/actual/link",
        "backgroundImageMobile": "/path/to/mobile-image.jpg",
        "backgroundImageDesktop": "/path/to/desktop-image.jpg",
        "backgroundColor": "bg-primary-blue",
        "theme": "light"
      }
    },
    {
      "componentType": "ContentTileGrid",
      "instanceName": "content-grid-1",
      "order": 2,
      "contentArea": "main",
      "fields": {
        "sectionHeading": "Featured Products"
      },
      "children": [
        {
          "componentType": "ContentTile",
          "instanceName": "tile-1",
          "fields": {
            "image": "/path/to/tile-image-1.jpg",
            "heading": "Product 1",
            "bodyText": "<p>Description of product 1</p>",
            "ctaText": "Learn More",
            "ctaLink": "/products/product-1"
          }
        },
        {
          "componentType": "ContentTile",
          "instanceName": "tile-2",
          "fields": {
            "image": "/path/to/tile-image-2.jpg",
            "heading": "Product 2",
            "bodyText": "<p>Description of product 2</p>",
            "ctaText": "Learn More",
            "ctaLink": "/products/product-2"
          }
        }
      ]
    }
  ],
  "extractedImages": [
    {
      "originalUrl": "https://example.com/images/hero.jpg",
      "localPath": "/tmp/website-download/example.com/images/hero.jpg",
      "type": "hero-background",
      "usedBy": ["HeroSection"]
    }
  ]
}
```

**C. Extraction rules:**

- **Text content**: Extract as-is, preserve HTML for richtext fields
- **Links**: Convert to relative paths when possible (e.g., `https://example.com/about` → `/about`)
- **Images**: Record both original URL and local downloaded path (if available)
- **Lists/Arrays**: For repeating components, extract **ALL instances** in order — do NOT take a representative subset or stop early. If a carousel has 9 cards, extract all 9. The goal is a pixel-perfect page recreation.
- **Empty/Missing fields**: Use `null` or empty string, don't skip
- **HTML entities**: Preserve (e.g., `&amp;`, `&nbsp;`)
- **Hardcoded lists** (footer links, country lists, social links, nav items): Extract every item as structured data — these must be populated dynamically via content properties, not hardcoded in component code

**D. Save to file:**

Save extracted content as: `$PROJECT_DIR/workflow-output/content-data.json`

This file will be consumed by `/create-content` to populate GraphQL mutations with actual content.

### Step 6.1: Verify Content Completeness (MANDATORY GATE)

Before proceeding to Step 7, verify every repeating section was fully extracted:

1. For each container/carousel/list section identified in Step 3, count the child items visible in the source HTML
2. Count the matching `children` entries in `componentInstances`
3. Build a verification table:

| Section Name | Items in HTML | Items Extracted | ✓/✗ |
|-------------|--------------|-----------------|-----|

4. **Every row must show matching counts.** If any section has fewer extracted items than HTML items, go back and extract the missing ones before continuing.
5. Also count items in hardcoded lists (navigation links, footer links, locale/country selectors, social links). Include these in the table.

**Do not proceed to Step 7 until all counts match.**

### Step 7: Generate Analysis Document

**Determine the project directory before saving:**

Find the Jahia module project root (contains `settings/definitions.cnd` or `package.json` with a `jahia` field):
1. Check if `settings/definitions.cnd` exists in the current directory → `PROJECT_DIR="."`
2. Otherwise search subdirectories: `find . -name "definitions.cnd" -path "*/settings/*" | head -1` and use its grandparent
3. If still not found, look for `package.json` files with a `jahia` key in `projects/*/` subdirectories
4. If ambiguous (multiple projects found), ask the user which project to use

**Save all analysis outputs to `$PROJECT_DIR/workflow-output/` folder:**
- Create the folder if it doesn't exist: `mkdir -p "$PROJECT_DIR/workflow-output"`
- Save component manifest as: `$PROJECT_DIR/workflow-output/component-manifest.json`
- Save analysis document as: `$PROJECT_DIR/workflow-output/analysis.md`
- Save asset inventory as: `$PROJECT_DIR/workflow-output/asset-inventory.json`
- Save content data as: `$PROJECT_DIR/workflow-output/content-data.json` (from Step 6)
- Save asset inventory as: `$PROJECT_DIR/workflow-output/asset-inventory.json`

**asset-inventory.json** must catalog ALL images and media found on the page:
- Organize by section: list every image URL under the section where it appears
- Include per-section counts (e.g., section "What's New" → 7 images)
- List all CDN/external domains used for images
- Include icons, logos, badges, and background images
- Include any images referenced in inline styles (background-image)

This is a **complete reference catalog**, not a list of files to copy. The `/import-website-assets` command decides what to copy locally, but the inventory must document every URL so `/create-content` can reference them.

Create a markdown document with:

**1. Executive Summary**
- Total HIGH-LEVEL sections identified
- Component breakdown (page-level, composite, simple)
- Complexity assessment

**2. Section Map**
Visual hierarchy showing:
```
Header Section
├── Logo Component
├── Navigation Menu
└── Search Box

Hero Section
├── Title Card
├── Image Gallery
└── CTA Button

Content Grid Section
├── Card Component (repeating)
│   ├── Image
│   ├── Title
│   └── Description

Footer Section
├── Link Columns
└── Social Links
```

**3. Component Specifications**
For each HIGH-LEVEL component:
- Detailed specification as described in Step 5
- **MUST include HTML Fragment** for each component
- **The HTML fragment MUST be extracted from /tmp/webpage.html, not written from memory**
- For container components: include the wrapper AND one complete child item

**4. Implementation Plan**
- Phase 1: Core layout components (Header, Footer, Section Container)
- Phase 2: Content sections (Hero, Grid, List)
- Phase 3: Sub-components (Card, Button, Link)

### Step 8: Create Visual Map

Generate a visual text-based map showing the page layout with numbered sections. This helps identify high-level components:

```
┌────────────────────────────────────────────────┐
│ [1] HEADER SECTION                             │
│     Utility Nav + Logo + Main Navigation       │
│     Interactive: Yes (dropdowns, mobile menu)  │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│ [2] HERO SECTION                               │
│     "Health plans that fit your life"          │
│     Content: h1 + paragraph + CTA + 3 images   │
│     Interactive: No                            │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│ [3] CONTENT GRID SECTION                       │
│     "Coverage you can count on"                │
│     Pattern: 4x Card (repeating)               │
│     Interactive: No                            │
└────────────────────────────────────────────────┘

TOTAL SECTIONS: 3 high-level components identified
```

### Step 8.1: Cross-Reference Validation (MANDATORY GATE)

Before presenting results, verify consistency across all output files:

1. **Manifest ↔ Content data**: Every component in component-manifest.json must have ≥1 matching `componentInstance` in content-data.json
2. **Manifest ↔ Analysis**: Every component in the manifest must have an HTML fragment in analysis.md
3. **Content data ↔ Assets**: Every image URL in content-data.json fields should appear in asset-inventory.json
4. **Field names**: Field names in content-data.json `fields` objects must match field names in component-manifest.json `fields` arrays

Report a validation summary table. Fix any gaps before presenting to the user.

| Check | Status | Details |
|-------|--------|---------|
| Manifest ↔ Content | ✓/✗ | N components, N instances |
| Manifest ↔ Analysis | ✓/✗ | N specs with HTML fragments |
| Content ↔ Assets | ✓/✗ | N image URLs resolved |
| Field names consistent | ✓/✗ | N mismatches found |

### Step 9: Present Results

- Show the component hierarchy
- Show the visual section map
- Present the total count of unique component types identified
  - Mobile-specific elements (drawers, mobile nav, mobile search) with distinct HTML structures are SEPARATE component types — do not merge them into the desktop parent
  - Each container type that holds a different child type is its own component (even if the wrapper HTML looks similar)
  - The total depends on site complexity — a simple landing page may have 5-8, a full homepage 12-25. Do not artificially reduce the count.
- Confirm that content data has been extracted and saved to `$PROJECT_DIR/workflow-output/content-data.json`
- Inform the user about next steps:
  1. Use `/import-website-assets` to import CSS, JS, and other assets (if website was downloaded)
  2. Use `/implement-components` to generate the component code
  3. Use `/create-content` to recreate the page with extracted content

## Next Steps

After analysis, the typical workflow is:

1. **Import Assets** (if website was downloaded):
   ```bash
   /import-website-assets
   ```
   This will import all CSS, JavaScript, images, and fonts into the `static/` folder.

2. **Implement Components**:
   ```bash
   /implement-components
   ```
   This will generate the Jahia component code based on the analysis.

ARGUMENTS: {URL or file path or "screenshot"}
