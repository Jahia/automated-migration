---
name: 1-analyze-website
description: Download and analyze a website to identify all Jahia components needed. Produces component manifest, content data, HTML fragments, and asset inventory. Use at the start of every migration.
allowed-tools: Bash, Read, Write, WebFetch
---

# Skill: Analyze Website

Turns a website into a structured Jahia component blueprint. Invoked by `/1-analyze`.

---

## Step 1: Obtain HTML content

**If URL given:**
```bash
mkdir -p /tmp/website-download
wget --recursive --level=2 --no-parent --convert-links \
     --adjust-extension --page-requisites --no-clobber \
     --user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
     --directory-prefix=/tmp/website-download "{URL}"
```

**If file path given:** Read directly.

Save raw HTML to `/tmp/webpage.html` (do NOT convert `class` → `className` — that happens in Step 7 per component).

---

## Step 2: Identify sections

Priority order:
1. `<section>` tags
2. `<article>` tags
3. `<header>`, `<footer>`, `<nav>`, `<main>`
4. `<div>` with classes matching: `hero`, `banner`, `wrapper`, `section`, `footer`, `navigation`, `menu`, `content`, `*-block`, `*-area`, `*-zone`
5. `<div>` with `role` attributes

---

## Step 3: Analyze each section

For each section:
- **Type:** Full section / Composite (with repeating children) / Simple
- **Interactivity:** Server-only / Client island (animations, state, event handlers)
- **Full-page URL?** Content with its own detail page needs `jmix:mainResource`
- **Absolute area?** Header and footer → `areaType: "absolute"` in manifest

---

## Step 4: Extract HTML fragment (critical)

1. Read `/tmp/webpage.html`, locate the component's root element
2. Copy the **complete HTML block** — every element, every attribute, every nesting level
3. For containers (carousels, grids): copy wrapper + **one complete child item**
4. Replace ONLY dynamic text/URLs with `{placeholders}`: `<h1>Actual</h1>` → `<h1>{heading}</h1>`
5. **NEVER** modify: CSS classes, `data-*`, `aria-*`, `role`, wrapper `<div>`s, `<noscript>`, `<source>`, inline `style`

**Self-check:** Count attributes in source vs your fragment. If yours is shorter, you simplified something — re-extract.

---

## Step 5: Extract content data

For each component instance, extract all actual content:

```json
{
  "componentType": "HeroSection",
  "instanceName": "hero",
  "order": 1,
  "contentArea": "main",
  "fields": {
    "heading": "Actual heading text",
    "bodyText": "<p>Actual body HTML</p>",
    "ctaText": "Button label",
    "ctaLink": "/about",
    "backgroundImage": "https://cdn.example.com/hero.jpg"
  }
}
```

Extract ALL instances of repeating components (all carousel cards, all list items — never a subset).

---

## Step 6: Mandatory verification gate

Before saving results:

| Check | Requirement |
|---|---|
| Manifest ↔ Content data | Every component has ≥1 content instance |
| Manifest ↔ Analysis | Every component has an HTML fragment |
| Content ↔ Assets | Every image URL in content-data is in asset-inventory |
| Field names | Field names in content-data match manifest field definitions |
| Repeating counts | Count children in HTML = count in content-data (all carousels, lists) |

Do not proceed until all checks pass.

---

## Step 7: Save outputs

Find project directory: `find . -name "definitions.cnd" -path "*/settings/*" | head -1` → grandparent.

```bash
mkdir -p $PROJECT_DIR/workflow-output
```

Save:
- `workflow-output/analysis.md` — component specs with HTML fragments
- `workflow-output/component-manifest.json` — structured list with fields and flags
- `workflow-output/content-data.json` — all extracted content
- `workflow-output/asset-inventory.json` — all images catalogued by section

---

## component-manifest.json structure

```json
{
  "components": [
    {
      "name": "HeroSection",
      "nodeType": "ns:heroSection",
      "displayName": "Hero Section",
      "areaType": "page",
      "needsFullPage": false,
      "interactive": false,
      "isContainer": false,
      "childType": null,
      "fields": [
        { "name": "heading", "type": "string", "i18n": true, "mandatory": true },
        { "name": "backgroundImage", "type": "weakreference, picker[type='image']", "mandatory": false }
      ]
    }
  ]
}
```

**Flags:**
- `areaType: "absolute"` → header/footer components (placed via AbsoluteArea in Layout.tsx)
- `needsFullPage: true` → content type with its own detail page URL (news articles, products)
- `interactive: true` → needs a `.client.tsx` island
- `isContainer: true` → has child components via `+ * (childType)`

---

## Validation checklist
- [ ] At least one section identified per major visible area of the page
- [ ] HTML fragment extracted from file (not written from memory)
- [ ] All repeating items fully extracted (not a sample)
- [ ] All image fields typed as `weakreference` in manifest (not `string`)
- [ ] Absolute area components identified (header, footer)
- [ ] Cross-reference validation table passed
- [ ] All 4 output files saved to `workflow-output/`
