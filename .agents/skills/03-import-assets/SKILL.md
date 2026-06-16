---
name: 3-import-assets
description: Copy CSS, JS, fonts, and images from the source site into the Jahia module static directory. Use after scaffolding and before implementing components.
type: technical
phase: 3
status: active
depends_on:
  - 4-define-content-types
allowed-tools: Bash, Read, Write
---

# Skill: Import Assets

Copies static assets from the source website into the module. Invoked by `/3-assets`.

---

## Agent identity
- **Agent name:** Assetron
- **Reference style:** Logistics / cargo
- **Signature line (en):** *"What they built, we carry over."*
- **Personality note:** Efficient and pragmatic. Prefers npm over manual downloads. Always verifies what arrived.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## Static folder structure

```
projects/<module-name>/static/
├── css/         # All stylesheets
├── js/          # All scripts
├── fonts/       # woff, woff2, ttf, eot, otf
└── assets/      # Images, icons, SVGs
```

---

## HARD STOP - verify source before copying anything

Before writing any CSS to the project, verify the source exists:

```bash
ls /tmp/website-download/
find /tmp/website-download/ -name "*.css" | head -20
```

If `/tmp/website-download/` does not exist or contains no `.css` files: **STOP. Do not write any CSS to the project.** Download the site first (see skill 01-analyze-website Step 1), or extract CSS from Chrome DevTools and save to `/tmp/website-download/`.

**Never write CSS from scratch.** Never approximate, reconstruct, or invent CSS rules. Every class name and style must be copied verbatim from the source. Fabricated CSS will be visually wrong and will not match the original site.

---

## Copy assets from downloaded source

```bash
SOURCE=/tmp/website-download/<domain>
PROJECT=$( find . -maxdepth 3 -name "definitions.cnd" -path "*/settings/*" | head -1 | xargs dirname | xargs dirname )
STATIC=$PROJECT/static

mkdir -p $STATIC/{css,js,fonts,assets}

# CSS
find "$SOURCE" -name "*.css" -type f | while read f; do cp "$f" "$STATIC/css/"; done

# JS
find "$SOURCE" -name "*.js" -type f ! -name "*.min.js" | while read f; do cp "$f" "$STATIC/js/"; done

# Fonts
find "$SOURCE" -type f \( -name "*.woff" -o -name "*.woff2" -o -name "*.ttf" -o -name "*.eot" -o -name "*.otf" \) | while read f; do cp "$f" "$STATIC/fonts/"; done

# Images
find "$SOURCE" -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.gif" -o -name "*.svg" -o -name "*.webp" -o -name "*.ico" \) | while read f; do cp "$f" "$STATIC/assets/"; done
```

---

## Extract inline styles and scripts

From the downloaded HTML, extract `<style>` blocks into `static/css/inline.css` and inline `<script>` blocks (no `src` attribute) into `static/js/inline.js`. These often contain critical initialization code.

```bash
# Check what's in the HTML
grep -o '<style[^>]*>.*</style>' /tmp/webpage.html | head -20
grep -o '<script>[^<]*</script>' /tmp/webpage.html | head -20
```

Write extracted content to the respective files.

---

## Wire into Layout.tsx

Load order matters: inline CSS must come before linked CSS; inline JS after linked JS.

```tsx
import {
  AbsoluteArea,
  AddResources,
  buildModuleFileUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { ReactNode } from "react";
import type { JCRNodeWrapper } from "org.jahia.services.content";

export const Layout = ({ children }: { children: ReactNode }) => {
  const { renderContext } = useServerContext();
  const siteHome = renderContext.getSite().getHome() as JCRNodeWrapper;

  return (
    <html lang="en">
      <head>
        {/* Inline CSS first — overrides must load before vendor */}
        <AddResources type="css" resources={buildModuleFileUrl("static/css/inline.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/main.css")} />
        {/* Add other CSS files here */}

        <AddResources type="javascript" resources={buildModuleFileUrl("static/js/inline.js")} />
        {/* Add other JS files here */}
      </head>
      <body>
        <AbsoluteArea path={`${siteHome.getPath()}/header`} name="header" />
        {children}
        <AbsoluteArea path={`${siteHome.getPath()}/footer`} name="footer" />
      </body>
    </html>
  );
};
```

**Never hardcode `/modules/<name>/...` paths** — always use `buildModuleFileUrl`.

---

## Expose static directories in package.json

```json
{
  "jahia": {
    "static-resources": "/dist/client,/dist/assets,/locales,/static/css,/static/js,/static/fonts,/static/assets"
  }
}
```

---

## Verify

```bash
grep -n "inline.css" src/templates/Layout.tsx
grep -n "inline.js" src/templates/Layout.tsx
```

Both must return results. If empty, the inline assets are not loaded.

---

## CSS framework conflict detection (MANDATORY)

> Full patterns reference: `.agents/context/jahia-css-framework-conflicts.md`

---

## Font Awesome Pro / vendor font conflict detection (MANDATORY)

After copying CSS, check for Font Awesome Pro declarations in imported files:

```bash
grep -r "Font Awesome 6 Pro\|Font Awesome 6 Sharp\|font-awesome.*pro" static/css/ | head -20
```

**If any match is found:** the site uses FA Pro, which requires a paid kit. The font-family names are declared in the CSS but the actual Pro woff2 files are not available. Without fixing this, all FA icons render as blank boxes.

**Fix — add `@font-face` remapping in Layout.tsx** to point Pro family names at FA Free CDN files. Place this `<style>` block AFTER all `<AddResources>` CSS imports so it overrides any `font-src` already declared in the imported CSS:

```tsx
{/* Remap FA6 Pro/Sharp font-family names to Free font files */}
<style dangerouslySetInnerHTML={{ __html: `
  @font-face {
    font-family: "Font Awesome 6 Pro";
    font-style: normal; font-weight: 900; font-display: block;
    src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");
  }
  @font-face {
    font-family: "Font Awesome 6 Pro";
    font-style: normal; font-weight: 400; font-display: block;
    src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-regular-400.woff2") format("woff2");
  }
  @font-face {
    font-family: "Font Awesome 6 Brands";
    font-style: normal; font-weight: 400; font-display: block;
    src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-brands-400.woff2") format("woff2");
  }
  @font-face {
    font-family: "Font Awesome 6 Sharp";
    font-style: normal; font-weight: 900; font-display: block;
    src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");
  }
` }} />
```

> Why: The browser matches `font-family` names exactly. Adding a CDN link for FA Free doesn't help because the imported CSS already declares `font-family: "Font Awesome 6 Pro"`. The `@font-face` remap forces that family name to resolve to the Free woff2 files.

---

## CSS grid structure detection (MANDATORY)

After copying CSS, scan for CSS grid declarations that affect header or navigation layout:

```bash
grep -n "grid-template\|grid-area\|display.*grid" static/css/*.css | grep -i "header\|nav\|navigation" | head -20
# Also check for grid areas applied to .navigation-main or similar selectors
grep -n "grid-area" static/css/*.css | head -20
```

**If grid declarations position the navigation as a grid child:** note this for skill 05-implement-navigation. The `ns:mainNavigation` view must then output the **complete header structure** (the grid container plus all sibling grid items: logo, dates headline, ticket CTA, nav). Rendering only the `<nav>` element will break the layout because the CSS grid parent won't exist.

---

## Override slider/carousel JS body manipulation (MANDATORY)

Source-site JavaScript carousel and slider libraries (Swiffy Slider, Swiper, Owl Carousel, Slick, etc.) often manipulate `document.body.style.height` or `document.body.style.overflow` during initialization. In a Jahia SSR context this causes the page body to be locked to the viewport height, making everything below the fold invisible and preventing scroll.

**Fix: add these two CSS rules inside the FA Pro remap `<style>` block in `Layout.tsx`** - they must load before any JS executes:

```css
/* Prevent source-site carousel/slider JS from locking body height */
body { height: auto !important; overflow-x: hidden; }
```

Place these lines at the TOP of the existing `<style dangerouslySetInnerHTML>` block, before the `@font-face` declarations.

**Detection:** after first deploy, open browser DevTools console and run:
```js
document.body.style.height
```
If this returns anything other than `""` (empty string), the slider JS set it. Add the override.

---

## Fallback images for image-rendering components (MANDATORY)

Every component that renders a JCR image must have a bundled static fallback. Without it, the component collapses to 0px height when no JCR content exists yet — which looks like a CSS failure, not a missing-content problem.

**During asset import, download representative images for each image-rendering component:**

```bash
mkdir -p static/assets/images
# Hero/carousel: download 2-3 real slide images from the source site
# Use Chrome MCP JS tool to extract real image URLs from the live DOM (bypasses CDN auth)
# Then curl directly:
curl -sL "<image-url>" -o static/assets/images/slide-1.jpg
```

**Naming convention:** `static/assets/images/<component-slug>-fallback.jpg` or numbered: `slide-1.jpg`, `slide-2.jpg`, `news-fallback.jpg`.

These become the `FALLBACK_IMAGES` constants used in component views (see skill 07).

---

## Validation checklist
- [ ] `static/css/`, `static/js/`, `static/fonts/`, `static/assets/images/` all populated
- [ ] `static/css/inline.css` and `static/js/inline.js` extracted
- [ ] Layout.tsx imports inline assets FIRST
- [ ] `buildModuleFileUrl` used for all resource paths (never hardcoded)
- [ ] `package.json` `jahia.static-resources` includes all static directories
- [ ] AbsoluteArea for header and footer in Layout.tsx body
- [ ] **FA Pro check run** — if Pro font-family found, `@font-face` remap added to Layout.tsx
- [ ] **CSS grid check run** — if nav is a grid child, flagged for skill 05
- [ ] **Fallback images downloaded** for every image-rendering component type
