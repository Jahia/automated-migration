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


### Imported `body{overflow:hidden}` traps scrolling

Many source themes set `body{overflow:hidden;height:100%}` (or `100vh`) because the original scrolled inside a JS-managed inner container. The migrated Jahia page has no such inner scroller, so this rule TRAPS the whole page at the top — you cannot scroll to lower components on the public site OR in jContent Page Builder. After importing CSS, ALWAYS add an override in `src/templates/global.css` (it bundles last and wins):

```css
html, body { overflow-x: hidden; overflow-y: auto !important; height: auto !important; }
```

Verify with a FIXED-viewport browser (not a full-page screenshot, which bypasses overflow): scroll and confirm `window.scrollY` actually changes. Also watch for `position:fixed`/`100vh` hero/background elements that overlay content.


### Watch for overloaded tokens + dark-bar text contrast

The tokenizer can map ONE token (e.g. `--color-bg`) onto BOTH a background (dark) and a text colour on dark bars (should be light) — flip it either way and something breaks. Don't re-point the token; instead force the correct text colour on the specific dark bars in `global.css` (e.g. `.top-navbar, .header-navigation { color:#fff !important }`), keeping any white-bg dropdown panels dark. Also restore expected sticky/fixed positioning the source had (e.g. a sticky social top-bar). Verify header/top-bar text contrast on the rendered dark theme — dark-on-dark text is a frequent migration miss.

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

## Load migration environment

```bash
ENV_FILE=$(find . -name "migration.env" | head -1)
if [ -z "$ENV_FILE" ]; then
  echo "ERROR: migration.env not found. Run /0-migration-start first."
  exit 1
fi
source "$ENV_FILE"
echo "Jahia: $JAHIA_URL | Site: $JAHIA_SITE_KEY | MCP: $MCP_AVAILABLE"
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

### CSS relative path rewriting (mandatory after every CSS import)

Imported CSS files contain relative `url(...)` references to fonts, images, and icons (e.g. `url('../fonts/fa-solid-900.woff2')`). These paths resolve correctly on the original CDN but break when the CSS is served from Jahia's `static/css/` path.

After copying any CSS file, run this rewrite pass:

```bash
CSS_DIR="projects/$MODULE_NAME/static/css"
CDN_BASE="<the CDN base URL the CSS was downloaded from, e.g. https://cdn.sialparis.com/styles>"

for css_file in "$CSS_DIR"/*.css; do
  echo "Rewriting paths in: $css_file"

  # Rewrite relative font paths → absolute CDN URLs
  sed -i.bak \
    -e "s|url('\.\./fonts/|url('${CDN_BASE}/../fonts/|g" \
    -e 's|url("\.\./fonts/|url("'"${CDN_BASE}"'/../fonts/|g' \
    -e "s|url('\.\./images/|url('${CDN_BASE}/../images/|g" \
    -e 's|url("\.\./images/|url("'"${CDN_BASE}"'/../images/|g' \
    -e "s|url('\.\./webfonts/|url('${CDN_BASE}/../webfonts/|g" \
    -e 's|url("\.\./webfonts/|url("'"${CDN_BASE}"'/../webfonts/|g' \
    "$css_file"

  rm -f "${css_file}.bak"
done
```

**Verify the rewrite worked:**
```bash
grep -n "url('\.\." "$CSS_DIR"/*.css | head -20
# Should return nothing — all relative paths should be gone
```

If relative paths remain, track down the CDN base URL for each CSS file and rewrite manually. A `url('../fonts/...')` in deployed CSS silently breaks every font and icon that CSS controls — it renders as fallback font or empty box with no error in the browser console.

**For Font Awesome specifically:** if the theme uses Font Awesome Pro (`fa-sharp`, `fa-light`, `fa-thin` prefixes), it cannot be replaced by the free CDN version — those glyph codes do not exist in FA Free. Check the CSS for Pro-exclusive prefixes:

```bash
grep -E "fa-sharp|fa-light|fa-thin|fa-duotone" "$CSS_DIR"/*.css | head -10
```

If found: the site uses FA Pro. You need either a FA Pro kit URL or the FA Pro webfont files. Note this as a dependency and ask the user for the FA Pro kit token before proceeding.

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
# Use the Chrome MCP JS tool to extract real image URLs from the live DOM (this also
# bypasses CDN/WAF auth). Then fetch through the cached, rate-limited helper rather
# than a bare curl — it caches under <project>/.reference/cache/, retries, and backs
# off if the CDN throttles:
FETCH="orchestration/lib/cached-fetch.sh"
SRC="$("$FETCH" fetch "$PROJECT_PATH" "<image-url>")" && cp "$SRC" static/assets/images/slide-1.jpg
```

> **WAF / VPN note:** these are *static fallback* assets bundled in the module. For **content** images that must land in Jahia's DAM, prefer the in-Jahia image proxy / importer (skills 01 and 09) — it fetches server-side with browser headers + Referer and is the most WAF-resistant path. If even the helper is blocked (exit 2), slow down (`RATE_DELAY=8`), use the browser to capture the URL, or import via the in-Jahia proxy. Never loop a bare `curl` against a blocking CDN.

**Naming convention:** `static/assets/images/<component-slug>-fallback.jpg` or numbered: `slide-1.jpg`, `slide-2.jpg`, `news-fallback.jpg`.

These become the `FALLBACK_IMAGES` constants used in component views (see skill 07).

---

## Tokenize CSS into theme variables (MANDATORY)

**Every migration must variabilize its CSS tokens.** The imported CSS ships with hardcoded colors and fonts; a re-theme would otherwise mean editing dozens of files. Instead, hoist all color and font literals into CSS custom properties on `:root` so the **entire site theme can be changed by overriding those variables** — with no code redeploy.

Run this AFTER CSS import + path rewrite, BEFORE the purge step:

```bash
# Variabilize colors + font stacks across all imported stylesheets.
# Writes the :root token layer to static/css/theme-tokens.css, rewrites every
# value to var(--token), and reports the palette for semantic naming.
python3 orchestration/lib/tokenize-css.py \
  --out static/css/theme-tokens.css \
  --report workflow-output/theme-tokens.md \
  static/css/*.css

cat workflow-output/theme-tokens.md   # review the palette
```

Then:
1. **Verify the semantic guesses** in `theme-tokens.css` — the tool labels the most frequent saturated colors `--color-primary/secondary/accent` and the dominant neutrals `--color-bg/--color-text`, but confirm `--color-primary` is the real brand color and rename/remap if not.
2. **Load `theme-tokens.css` FIRST** in `Layout.tsx` (before the bundled CSS that consumes the vars). See skill 08 — the Layout also emits the runtime overrides below.

### Two ways to re-theme at runtime (both wired in Layout — skill 08)

The harness ships **both** override paths so a site can be re-themed by an editor, not a developer:

**A) Site-node theme mixin** — quick token tweaks from jContent. Declare in `settings/definitions.cnd` (the scaffold ships this; add the property set to match your semantic tokens):

```
[<ns>mix:siteTheme] mixin
 - themePrimaryColor (string)
 - themeSecondaryColor (string)
 - themeAccentColor (string)
 - themeTextColor (string)
 - themeBackgroundColor (string)
 - themeFontHeading (string)
 - themeFontBody (string)
 - themeOverrideCss (weakreference, picker[type='file'])
```

Add the mixin to the **site node** (`/sites/<siteKey>`, type `jnt:virtualsite`) so editors get the theme fields. The Layout reads these props and emits an inline `:root{}` that overrides the defaults from `theme-tokens.css`.

```bash
# add the mixin to the site node via MCP (one-time, per site)
curl -s -X POST "$JAHIA_HOST/modules/mcp" -u "$JAHIA_USER" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"content.update","arguments":{
    "path":"/sites/'"$JAHIA_SITE_KEY"'","locale":"en","addMixins":["<ns>mix:siteTheme"]}}}'
```

**B) Uploaded override stylesheet** — full re-skin without a deploy. The `themeOverrideCss` weakreference points to a `.css` file uploaded into Jahia's DAM; the Layout links it **last** so its rules win. An editor uploads a CSS file (typically just a `:root{}` block overriding the tokens, or any rule overrides) and points the site at it.

> Run the tokenizer BEFORE purge. Exclude `theme-tokens.css` from PurgeCSS input (it defines the `:root` variables used everywhere; purging would strip them).

---

## Step 5: Optimize imported assets for Jahia

Run this optimization pass AFTER all assets are imported and paths are rewritten. It reduces bundle size and prevents JS conflicts with React.

### 5a: CSS purging (remove unused rules)

A typical migration site ships 300-500KB of CSS. After purging against the actual component TSX output, 60-80% is typically dead code from pages and sections not being migrated.

```bash
# Install PurgeCSS if not present
npx purgecss --version 2>/dev/null || npm install -g purgecss

# Run purge against all compiled TSX component files
# The safelist preserves:
#   - Jahia edit-mode classes (jahia-*)
#   - Bootstrap responsive classes (col-*, d-*, flex-*)
#   - JavaScript-toggled state classes (active, open, is-*, has-*, show, hide, visible, hidden)
#   - Font Awesome classes (fa-*, fas, fab, etc.)

# Exclude theme-tokens.css — it defines the :root variables used everywhere; purging would strip them.
npx purgecss \
  --css $(ls static/css/*.css | grep -v 'theme-tokens.css') \
  --content "src/**/*.tsx" "src/**/*.ts" "src/**/*.jsx" \
  --safelist \
    ":root" \
    "/^--/" \
    "/^jahia/" \
    "/^col-/" \
    "/^d-/" \
    "/^flex-/" \
    "/^offset-/" \
    "/^order-/" \
    "/^align-/" \
    "/^justify-/" \
    "/^text-/" \
    "/^bg-/" \
    "/^is-/" \
    "/^has-/" \
    "/^active$/" \
    "/^open$/" \
    "/^show$/" \
    "/^hide$/" \
    "/^visible$/" \
    "/^hidden$/" \
    "/^fa/" \
    "/^swiper/" \
    "/^slick/" \
  --output static/css/

echo "CSS purge complete. Size before/after:"
du -sh static/css/ 2>/dev/null || ls -la static/css/
```

**Important:** Run purge AFTER skill 07 completes all components, not before — otherwise TSX files do not exist yet and purge will remove everything. If running skill 03 before component implementation, skip this step and return here after skill 07.

**If purge removes too much** (layout breaks after deploy): add the broken class names to the safelist above and re-run. Do not revert to the full CSS — fix the safelist instead.

---

### 5b: Classify CSS as global vs component-scoped

The imported CSS mixes two concerns. Pre-classify so component agents in skill 07 know where to look:

```bash
python3 - << 'EOF'
import re, os, glob

css_files = glob.glob('static/css/*.css')
global_patterns = [
    r'^(html|body|:root|\*|\.container|\.row|\.col)',   # reset, grid, layout
    r'^@(font-face|keyframes|import)',                    # fonts, animations
    r'^\.(navbar|header|footer|nav-)',                    # global nav/footer
    r'^\.(btn|form-|input|select|textarea)',              # global form/button base
]
component_hint = []

for f in css_files:
    with open(f) as fh:
        content = fh.read()
    selectors = re.findall(r'^([.#][a-zA-Z][^\s{,]+)', content, re.MULTILINE)
    for sel in selectors:
        is_global = any(re.match(p, sel) for p in global_patterns)
        if not is_global and len(sel) > 5:
            component_hint.append(sel.strip())

# Write a hint file for component agents
os.makedirs('workflow-output', exist_ok=True)
with open('workflow-output/component-css-selectors.txt', 'w') as f:
    f.write('\n'.join(sorted(set(component_hint))))

print(f"Found {len(set(component_hint))} potentially component-scoped CSS selectors.")
print("Written to workflow-output/component-css-selectors.txt")
print("Component agents (skill 07) should pull from this list when building .module.css files.")
EOF
```

This file is read by skill 07 component agents to know which CSS selectors to include in each component's `.module.css`.

---

### 5c: Audit JS files for React conflicts

JS files that manipulate the DOM directly can conflict with React's reconciliation. Identify risky patterns before component implementation begins:

```bash
echo "=== JS conflict audit ==="
echo ""

echo "-- Carousel / slider init (will conflict with SSR — move to .client.tsx island) --"
grep -rn "new Swiper\|\.slick(\|new Splide\|swiffy\|new Glide\|\.carousel(" static/js/ 2>/dev/null || echo "  none found"

echo ""
echo "-- Direct DOM manipulation on load (will fight React hydration) --"
grep -rn "document\.querySelector\|document\.getElementById\|\.innerHTML\s*=" static/js/ 2>/dev/null | grep -v "//.*document" | head -20 || echo "  none found"

echo ""
echo "-- Event listeners added to static DOM nodes (safe only if React doesn't own those nodes) --"
grep -rn "addEventListener\|\.on(" static/js/ 2>/dev/null | grep -v "//.*addEventListener" | head -20 || echo "  none found"

echo ""
echo "-- Form submit handlers (replace with React form components) --"
grep -rn "\.submit(\|form\.addEventListener\|ajaxForm\|$.ajax" static/js/ 2>/dev/null || echo "  none found"
```

For each hit, decide:
- **Carousel/slider init**: the component must be a `.client.tsx` island — add `interactive: true` in `component-manifest.json`
- **DOM manipulation on load**: wrap in `if (typeof window !== 'undefined')` guard in a client island
- **Event listeners on Jahia structural nodes** (header, footer): safe to keep in global JS, but guard with `?.`
- **Form submit handlers**: replace entirely with React-controlled form components

Write the findings to `workflow-output/js-conflict-report.txt`:

```bash
{
  echo "JS Conflict Audit"
  echo "================="
  echo ""
  echo "Carousel/slider:"
  grep -rn "new Swiper\|\.slick(\|new Splide\|swiffy\|new Glide\|\.carousel(" static/js/ 2>/dev/null || echo "  none"
  echo ""
  echo "DOM manipulation:"
  grep -rn "document\.querySelector\|document\.getElementById\|\.innerHTML\s*=" static/js/ 2>/dev/null | grep -v "//" | head -30 || echo "  none"
} > workflow-output/js-conflict-report.txt

echo "Report written to workflow-output/js-conflict-report.txt"
cat workflow-output/js-conflict-report.txt
```

Present the conflict report to the user. For each carousel library found, confirm the corresponding component should be flagged `interactive: true` in the manifest (or add the flag now if the manifest already exists).

---

### 5d: Edit-mode safety — add Jahia class safeguards to Layout.tsx

Jahia's page builder injects CSS classes onto rendered nodes (e.g., `jahia-node-draggable`, `jahia-editable`, `jahia-highlight`). If any imported CSS uses overly broad selectors like `div *` or `[class*="jahia"]`, it can break the editor UI.

```bash
echo "Checking for broad selectors that could affect Jahia edit-mode classes..."
grep -n '\[class\*=\|div \* \|> \* \|\.jahia' static/css/*.css 2>/dev/null || echo "No risky selectors found."
```

If any `[class*=...]` wildcard selectors are found that could match `jahia-*` class names, add a CSS override at the END of the last imported stylesheet:

```css
/* Jahia edit-mode safety — keep editor overlays intact */
[class*="jahia-"] {
  all: unset !important;
  display: revert !important;
}
```

Only add this override if the audit actually finds conflicting selectors. Do not add it preemptively.

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
- [ ] CSS purge run (or deferred to after skill 07) — size reduction noted
- [ ] workflow-output/component-css-selectors.txt written
- [ ] workflow-output/js-conflict-report.txt written — carousel components flagged as interactive: true
- [ ] Edit-mode safety override added if broad selectors found

## Scroll-reveal animations: content hidden at `opacity:0` until JS adds a reveal class

Imported themes routinely hide components until they scroll into view, with rules like:
```css
.content-block:not(.slide-in) .img-cover { transform: translateY(5rem); opacity: 0; }
```
The element only becomes visible once a reveal class (commonly `.slide-in`) is added to the component by an IntersectionObserver in the theme's JS. In a migrated module that theme JS is usually NOT loaded, so **every animated component stays invisible forever** — symptom: "I see the images in the source but they don't render." (`naturalWidth` is fine; computed `opacity` is 0.)

Find every reveal selector and its trigger class:
```bash
grep -aoE "\.[a-z][a-z0-9-]*(\.[a-z-]+)?:not\(\.slide-in\)" static/css/main-theme.css | sed 's/:not(.slide-in)//' | sort -u
```
Then add a small **self-contained IntersectionObserver in `Layout.tsx`** (don't load the whole theme JS — it usually has jQuery/other deps and side effects) that adds the reveal class to those component selectors on intersection. Two musts:
- **Edit mode**: reveal everything immediately (`renderContext.isEditMode()` → add the class on load) so the Page Builder isn't full of blank sections.
- **Safety fallback**: a `setTimeout` that reveals anything still hidden after a few seconds, so a missed/failed observer never leaves content permanently invisible.
