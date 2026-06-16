---
name: 3-import-assets
description: Import CSS, JS, fonts, and images from the source website into the Jahia module's static/ folder. Wires them into Layout.tsx via AddResources.
allowed-tools: Bash, Read, Write, Edit
---

# Skill: Import Assets

Copies static assets from the source website into the module. Invoked by `/3-assets`.

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

## Validation checklist
- [ ] `static/css/`, `static/js/`, `static/fonts/`, `static/assets/` all populated
- [ ] `static/css/inline.css` and `static/js/inline.js` extracted
- [ ] Layout.tsx imports inline assets FIRST
- [ ] `buildModuleFileUrl` used for all resource paths (never hardcoded)
- [ ] `package.json` `jahia.static-resources` includes all static directories
- [ ] AbsoluteArea for header and footer in Layout.tsx body
