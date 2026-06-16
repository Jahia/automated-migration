---
description: Implement Layout.tsx with AbsoluteArea for header/footer, page template variants, and MainResource template
---

## State management (run at start and end)

**At the START of this step — PREREQUISITE CHECK:**
```bash
STATE="$PROJECT_PATH/workflow-output/state.json"
[ -f "$STATE" ] || { echo "ERROR: state.json missing — run /2-scaffold first"; exit 1; }

SCAFFOLD_STATUS=$(jq -r '.steps["2-scaffold"].status' "$STATE")
[ "$SCAFFOLD_STATUS" = "completed" ] || { echo "ERROR: step 2-scaffold not completed (status: $SCAFFOLD_STATUS)"; exit 1; }

# Verify src/ exists
[ -d "$PROJECT_PATH/src" ] || { echo "ERROR: src/ directory missing — scaffold may have failed"; exit 1; }

jq '.steps["4-templates"].status = "in_progress"' "$STATE" > /tmp/state.tmp && mv /tmp/state.tmp "$STATE"
```

**At the END of this step:**
```bash
# Verify outputs
LAYOUT_OK=$(grep -l "AbsoluteArea" "$PROJECT_PATH/src/templates/Layout.tsx" 2>/dev/null && echo "yes" || echo "NO")
BASIC_OK=$([ -f "$PROJECT_PATH/src/templates/Page/basic.server.tsx" ] && echo "yes" || echo "NO")

jq --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
   --arg notes "Layout AbsoluteArea: $LAYOUT_OK, basic template: $BASIC_OK" \
   '.steps["4-templates"] = {"status": "completed", "completedAt": $ts, "notes": $notes}' \
   "$STATE" > /tmp/state.tmp && mv /tmp/state.tmp "$STATE"

cat >> "$PROJECT_PATH/workflow-output/migration-log.md" << EOF

## [$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Step 4 — Page Templates — COMPLETED
- **Layout AbsoluteArea:** $LAYOUT_OK
- **basic.server.tsx:** $BASIC_OK
EOF

[ "$LAYOUT_OK" = "NO" ] && echo "WARNING: AbsoluteArea not found in Layout.tsx — header/footer will not render"
```

---

> See full skill guide at `.agents/skills/08-page-templates/SKILL.md`

Implement the template set by editing the Layout file to include all CSS and JavaScript files that were previously imported into the static folder.

## ⚠️ CRITICAL WARNING

**DO NOT SKIP THIS STEP!** After running `/import-website-assets`, the inline CSS and JavaScript files extracted from the original HTML **MUST** be imported into Layout.tsx. Forgetting this is the #1 most common error!

**Always verify inline assets are imported:**
```bash
grep -n "inline.css" src/templates/Layout.tsx
grep -n "inline.js" src/templates/Layout.tsx
```

If these commands return nothing, the inline assets are NOT imported and your site will be missing critical styles and scripts!

## Overview

This command is executed after `/import-website-assets` in the workflow. It:
1. Locates the JS project and Layout file
2. Scans the static folder for CSS and JS files (including **inline.css** and **inline.js**)
3. Generates `AddResources` entries for each file
4. Updates the Layout file with the necessary imports and resources
5. **Ensures inline.css and inline.js are loaded FIRST** (before other static files)
6. **Matches the body structure to the source HTML** (preserves classes, IDs, and wrapper elements)

## Instructions

### Step 1: Detect JS Project

**Find the JS project folder:**

The repo may contain multiple JS projects. Detect the correct project by looking for folders with `package.json` that have a `jahia` field:

```bash
# Find all JS projects in the repo
find . -maxdepth 2 -name "package.json" -type f
```

For each found package.json, check if it has a `jahia` field:
```bash
# Check for jahia field
grep -l '"jahia"' ./*/package.json
```

**Determine the project path:**
- If only one JS project exists, use that
- If multiple exist, ask the user which project to work with
- Common patterns: `./addemo/`, `./[projectname]/`, etc.

**Set PROJECT_PATH variable:**
```bash
# Example: If the project is in addemo/
PROJECT_PATH="./addemo"
```

### Step 2: Locate or Create Layout File

**Check for existing Layout file:**

```bash
# Look for Layout file in src/templates/
find "$PROJECT_PATH/src/templates" -name "Layout.*" -type f 2>/dev/null
```

**Possible locations:**
- `$PROJECT_PATH/src/templates/Layout.tsx`
- `$PROJECT_PATH/src/templates/Layout.jsx`
- `$PROJECT_PATH/src/templates/base/Layout.tsx`

**If Layout file doesn't exist:**

Ask the user if they want to:
1. Create a new Layout.tsx file
2. Specify a different file path
3. Skip this step

**If creating a new Layout file:**

Create `$PROJECT_PATH/src/templates/Layout.tsx` with the basic structure:

```tsx
import {
  AddResources,
  buildModuleFileUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { ReactNode } from "react";

import "modern-normalize/modern-normalize.css";
import "./global.css";

/** Places `children` in an html page. */
export const Layout = ({ title, children }: { title: string; children: ReactNode }) => {
  const { currentResource } = useServerContext();
  const lang = currentResource.getLocale().getLanguage();
  return (
    <html lang={lang}>
      <head>
        {/* Static CSS resources will be added here */}
        {/* Static JS resources will be added here */}
        <title>{title}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </head>
      <body>{children}</body>
    </html>
  );
};
```

Also create `$PROJECT_PATH/src/templates/global.css` if it doesn't exist (can be empty or with base styles).

**Set LAYOUT_FILE variable:**
```bash
LAYOUT_FILE="$PROJECT_PATH/src/templates/Layout.tsx"
```

### Step 2b: Wire Absolute Areas for Header and Footer

**What are absolute areas?**
Absolute areas are site-level editorial zones shared across ALL pages. Header and footer components must live here — not as components dropped on each individual page. They are rendered once from a single location in the JCR (`/sites/{siteKey}/home/header`, `/sites/{siteKey}/home/footer`) and appear on every page automatically.

**Check if the component manifest has absolute-area components:**
```bash
jq '[.components[] | select(.areaType == "absolute")]' workflow-output/component-manifest.json 2>/dev/null || echo "No manifest found"
```

**If absolute-area components exist**, add `<AbsoluteArea>` calls to `Layout.tsx` instead of rendering header/footer as regular page-area components.

**Layout.tsx pattern with absolute areas:**
```tsx
import {
  AbsoluteArea,
  AddResources,
  buildModuleFileUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ReactNode } from "react";

export const Layout = ({ children }: { children: ReactNode }) => {
  const { renderContext } = useServerContext();
  const siteHome = renderContext.getSite().getHome() as JCRNodeWrapper;

  return (
    <html lang="en">
      <head>
        {/* CSS and JS resources */}
      </head>
      <body>
        {/* Header — editable only from the home page, read-only everywhere else */}
        <AbsoluteArea
          name="header"
          parent={siteHome}
          nodeType="namespace:siteHeader"
          numberOfItems={1}
          readOnly="children"
        />

        {/* Page-specific content */}
        <main>
          {children}
        </main>

        {/* Footer — editable only from the home page */}
        <AbsoluteArea
          name="footer"
          parent={siteHome}
          nodeType="namespace:siteFooter"
          numberOfItems={1}
          readOnly="children"
        />
      </body>
    </html>
  );
};
```

**Key parameters:**
- `name` — JCR node name under which the area content is stored (e.g., `/sites/siteKey/home/header`)
- `parent={siteHome}` — anchors the area to the home page so it's shared across all pages
- `nodeType` — restricts what component type editors can add (e.g., only `namespace:siteHeader`)
- `numberOfItems={1}` — single component only (no list)
- `readOnly="children"` — editors can configure from the home page, but the area appears read-only on all other pages

**Note:** Components flagged `areaType: "absolute"` in the manifest are created once via `/create-content` as children of the home page (`/sites/{siteKey}/home/header` and `/sites/{siteKey}/home/footer`), NOT in each page's `main` area.

### Step 2c: Add SEO Meta Tags, Favicon, and Accessibility to Layout.tsx

A production `Layout.tsx` must include head metadata, a favicon, and an accessibility skip link. These are not optional — they are required for every site.

**Update `Layout.tsx` to include:**

```tsx
import {
  AbsoluteArea,
  AddResources,
  buildModuleFileUrl,
  getNodeProps,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

// Import favicon at build time so Vite resolves the path
import favicon from "/static/assets/favicon.png";  // adjust extension/path as needed

type SeoProps = {
  "jcr:title"?: string;
  "jcr:description"?: string;
  seoKeywords?: string[];
  openGraphImage?: JCRNodeWrapper;
};

export const Layout = ({ children }: { children: ReactNode }) => {
  const { renderContext, mainNode } = useServerContext();
  const { t } = useTranslation();
  const siteHome = renderContext.getSite().getHome() as JCRNodeWrapper;

  // Read SEO properties from the current page node
  const {
    "jcr:title": pageTitle,
    "jcr:description": pageDescription,
    seoKeywords,
    openGraphImage,
  } = getNodeProps(mainNode as JCRNodeWrapper, [
    "jcr:title",
    "jcr:description",
    "seoKeywords",
    "openGraphImage",
  ]) as SeoProps;

  const siteTitle = renderContext.getSite().getTitle();
  const fullTitle = pageTitle ? `${pageTitle} | ${siteTitle}` : siteTitle;
  const canonicalUrl = (mainNode as JCRNodeWrapper).getAbsoluteUrl(renderContext.getRequest());

  return (
    <html lang={renderContext.getMainResourceLocale().getLanguage()}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />

        {/* Page title */}
        <title>{fullTitle}</title>

        {/* SEO meta */}
        {pageDescription && <meta name="description" content={pageDescription} />}
        {seoKeywords && seoKeywords.length > 0 && (
          <meta name="keywords" content={seoKeywords.join(", ")} />
        )}

        {/* Canonical URL */}
        <link rel="canonical" href={canonicalUrl} />

        {/* Open Graph */}
        <meta property="og:title" content={fullTitle} />
        <meta property="og:site_name" content={siteTitle} />
        <meta property="og:type" content="website" />
        <meta property="og:url" content={canonicalUrl} />
        {pageDescription && <meta property="og:description" content={pageDescription} />}
        {openGraphImage && (
          <meta property="og:image" content={(openGraphImage as JCRNodeWrapper).getAbsoluteUrl(renderContext.getRequest())} />
        )}

        {/* Favicon */}
        <link rel="icon" href={buildModuleFileUrl(favicon)} />

        {/* CSS and JS resources — AddResources calls go here */}
        <AddResources type="css" resources={buildModuleFileUrl("dist/assets/style.css")} />
      </head>
      <body>
        {/* Skip-to-content — accessibility requirement */}
        <a href="#main-content" className="sr-only focus:not-sr-only">
          {t("skipToContent")}
        </a>

        {/* Absolute area: header */}
        <AbsoluteArea
          name="header"
          parent={siteHome}
          nodeType="namespace:siteHeader"
          numberOfItems={1}
          readOnly="children"
        />

        <main id="main-content">
          {children}
        </main>

        {/* Absolute area: footer */}
        <AbsoluteArea
          name="footer"
          parent={siteHome}
          nodeType="namespace:siteFooter"
          numberOfItems={1}
          readOnly="children"
        />
      </body>
    </html>
  );
};
```

**Required locale key** — add to `settings/locales/en.json` and `fr.json`:
```json
{ "skipToContent": "Skip to main content" }
```
```json
{ "skipToContent": "Aller au contenu principal" }
```

**Favicon placement:** Place the favicon file in `static/assets/` (already served by the module). Common formats: `.png` (32×32), `.ico`, or `.svg`.

**Notes:**
- `getNodeProps()` returns `undefined` for missing properties — all destructured fields are optional types, so guard before using (`pageDescription && ...`)
- `mainNode` is the current page's primary resource — use it for SEO, not `currentNode` (which may be the component being rendered)
- The `canonicalUrl` requires an HTTP request context and works only in server rendering — it is fine to use in `Layout.tsx`
- If `favicon` import fails at build time, the favicon file doesn't exist in `static/assets/` — add a placeholder or adjust the path

### Step 3: Scan Static Folder for Resources

**List all CSS files:**

```bash
# Find all CSS files in static/css/
find "$PROJECT_PATH/static/css" -name "*.css" -type f 2>/dev/null | sort
```

Store the list of CSS files (just the filenames, not full paths).

**List all JavaScript files:**

```bash
# Find all JS files in static/js/
find "$PROJECT_PATH/static/js" -name "*.js" -type f 2>/dev/null | sort
```

Store the list of JS files (just the filenames, not full paths).

**Count resources:**
```bash
CSS_COUNT=$(find "$PROJECT_PATH/static/css" -name "*.css" -type f 2>/dev/null | wc -l)
JS_COUNT=$(find "$PROJECT_PATH/static/js" -name "*.js" -type f 2>/dev/null | wc -l)

echo "Found $CSS_COUNT CSS files and $JS_COUNT JS files"
```

**Handle no files found:**
- If no files are found in static folder, inform the user that `/import-website-assets` should be run first
- Ask if they want to continue anyway or exit

### Step 4: Generate AddResources Entries

**For each CSS file, generate:**

```tsx
<AddResources type="css" resources={buildModuleFileUrl("static/css/filename.css")} />
```

**For each JS file, generate:**

```tsx
<AddResources type="javascript" resources={buildModuleFileUrl("static/js/filename.js")} />
```

**Example generated code:**

```tsx
{/* ⚠️ CRITICAL: Inline CSS MUST be loaded FIRST */}
<AddResources type="css" resources={buildModuleFileUrl("static/css/inline.css")} />

{/* Other CSS Resources */}
<AddResources type="css" resources={buildModuleFileUrl("static/css/main.css")} />
<AddResources type="css" resources={buildModuleFileUrl("static/css/theme.css")} />
<AddResources type="css" resources={buildModuleFileUrl("static/css/components.css")} />

{/* ⚠️ CRITICAL: Inline JavaScript MUST be loaded FIRST */}
<AddResources type="javascript" resources={buildModuleFileUrl("static/js/inline.js")} />

{/* Other JavaScript Resources */}
<AddResources type="javascript" resources={buildModuleFileUrl("static/js/jquery.min.js")} />
<AddResources type="javascript" resources={buildModuleFileUrl("static/js/bootstrap.min.js")} />
<AddResources type="javascript" resources={buildModuleFileUrl("static/js/main.js")} />
```

**Ordering considerations (CRITICAL):**
1. **inline.css MUST be the FIRST CSS file** - Contains base styles from original HTML
2. **inline.js MUST be the FIRST JavaScript file** - Contains initialization code from original HTML
3. CSS files are typically loaded before JavaScript
4. JS files should be ordered by dependency (e.g., jQuery before plugins)
5. If order matters, inform the user they may need to manually reorder files

**Special handling for inline assets:**
- When scanning for CSS files, **prioritize inline.css** and place it first
- When scanning for JS files, **prioritize inline.js** and place it first
- Add clear comments indicating these are extracted inline assets
- Verify both files exist before generating imports (they should be created by /import-website-assets)

### Step 5: Check Existing AddResources Entries

**Read the current Layout file:**

```bash
cat "$LAYOUT_FILE"
```

**Check if AddResources already exist:**
- Look for existing `<AddResources` tags
- Check if any static resources are already referenced
- Count how many resources are already included

**Ask user for action:**
- **Replace all**: Remove existing AddResources and add all new ones
- **Append**: Keep existing and add new ones (may cause duplicates)
- **Merge**: Keep existing and only add files that aren't already referenced
- **Cancel**: Exit without making changes

### Step 6: Ensure Required Imports

**Check if the Layout file has the required imports:**

The file needs these imports at the top:

```tsx
import {
  AddResources,
  buildModuleFileUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { ReactNode } from "react";
```

**If imports are missing:**
- Add them at the top of the file
- Preserve any existing imports

**If imports already exist:**
- Don't duplicate them
- Ensure they include `AddResources` and `buildModuleFileUrl`

### Step 7: Update Layout File with Resources

**Locate the insertion point:**

Find the `<head>` section in the Layout file. The AddResources entries should be placed after any existing style imports but before the `<title>` tag.

**Pattern to look for:**
```tsx
<head>
  {/* Insert CSS resources here */}
  {/* Insert JS resources here */}
  <title>
```

**Insert the generated AddResources entries:**

1. Create a backup of the original file (optional but recommended)
2. Use the Edit tool to insert the resources
3. Place CSS resources first, then JS resources
4. Add helpful comments to organize sections

**Example structure:**
```tsx
<head>
  {/* Imported Static CSS Resources */}
  <AddResources type="css" resources={buildModuleFileUrl("static/css/main.css")} />
  <AddResources type="css" resources={buildModuleFileUrl("static/css/theme.css")} />

  {/* Imported Static JavaScript Resources */}
  <AddResources type="javascript" resources={buildModuleFileUrl("static/js/app.js")} />

  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
</head>
```

**Handle different modes:**

**Replace mode:**
- Remove all existing `<AddResources>` tags that reference static folder
- Insert all new resources

**Append mode:**
- Keep all existing resources
- Add new resources at the end of the head section

**Merge mode:**
- Keep existing resources
- Only add resources that don't already exist
- Check filename matches to avoid duplicates

### Step 8: Match Original HTML Body Structure

**⚠️ CRITICAL: The body tag and main content wrapper MUST match the original HTML structure**

After adding the CSS and JS resources, you must update the Layout file to wrap `{children}` in the same HTML structure as the source website. This ensures that:
- CSS selectors target the correct elements
- JavaScript finds the expected DOM structure
- The page renders identically to the original

**Find the source HTML file:**

```bash
# Look for downloaded HTML files
find "$PROJECT_PATH/.." -name "*.html" -type f | grep -v node_modules | head -5
```

Common locations:
- Parent directory of the project
- `../downloads/` or `../source/`
- Additional working directories
- Ask user if multiple HTML files are found

**Extract body tag structure:**

```bash
# Extract the opening body tag and first 30 lines of content
sed -n '/<body/,+30p' path/to/source.html | head -40
```

**Analyze the structure to identify:**

1. **Body tag attributes:**
   - Classes: `<body class="template-home">` → use `className="template-home"`
   - IDs: `<body id="main-body">` → use `id="main-body"`
   - Other attributes to preserve

2. **Main content wrapper:**
   - Look for `<main>` tag with id/class: `<main id="main">`
   - Look for container divs: `<div class="container-fluid">`
   - Look for article/section wrappers
   - Common patterns:
     ```html
     <body class="template-home">
       <main id="main">
         <div class="container-fluid">
           <!-- page content here -->
         </div>
       </main>
     </body>
     ```

3. **Elements to preserve:**
   - Skip header/footer (these are usually separate components)
   - Focus on the main content wrapper where `{children}` will be rendered
   - Preserve exact class names and IDs

**Update the Layout body section:**

**Before (default structure):**
```tsx
<body>{children}</body>
```

**After (matching source HTML):**
```tsx
<body className="template-home">
  <main id="main">
    <div className="container-fluid">
      {children}
    </div>
  </main>
</body>
```

**Implementation steps:**

1. Read the current Layout file body section
2. Identify the pattern from source HTML
3. Use the Edit tool to replace the body content
4. Ensure proper JSX syntax:
   - Use `className` instead of `class`
   - Self-closing tags must have `/>`
   - Proper nesting and indentation

**Example transformation:**

Source HTML:
```html
<body class="page-template" data-theme="light">
  <div id="root">
    <div class="app-container">
      <!-- content -->
    </div>
  </div>
</body>
```

Updated Layout.tsx:
```tsx
<body className="page-template" data-theme="light">
  <div id="root">
    <div className="app-container">
      {children}
    </div>
  </div>
</body>
```

**Common patterns to look for:**

1. **Bootstrap/container pattern:**
   ```html
   <body>
     <main>
       <div class="container-fluid">
         <!-- content -->
       </div>
     </main>
   </body>
   ```

2. **Wrapper with ID pattern:**
   ```html
   <body>
     <div id="app" class="wrapper">
       <!-- content -->
     </div>
   </body>
   ```

3. **Semantic HTML5 pattern:**
   ```html
   <body>
     <main id="main" role="main">
       <div class="content">
         <!-- content -->
       </div>
     </main>
   </body>
   ```

**Verification:**

After updating, verify the structure matches:
```bash
# Compare body structure
grep -A 5 "<body" "$LAYOUT_FILE"
grep -A 5 "<body" path/to/source.html
```

**Important notes:**

- Preserve exact class names - they are needed for CSS selectors
- Keep IDs intact - JavaScript may target these elements
- Maintain nesting order - some CSS uses child/descendant selectors
- Don't include header/footer elements - these are separate components
- Focus only on the main content wrapper where components will render

### Step 9: Verify the Changes

**After editing, verify the Layout file:**

```bash
# Check if the file has proper syntax
grep -c "AddResources" "$LAYOUT_FILE"
grep -c "buildModuleFileUrl" "$LAYOUT_FILE"
```

**Count added resources:**
```bash
# Count CSS resources
grep -c 'type="css"' "$LAYOUT_FILE"

# Count JS resources
grep -c 'type="javascript"' "$LAYOUT_FILE"
```

**Check for syntax errors:**
- Ensure all tags are properly closed
- Check for balanced braces `{}`
- Verify quotes are properly escaped

### Step 10: Optional - Update TypeScript Configuration

If the project doesn't have proper types for the imports, you may need to check `tsconfig.json`:

```bash
cat "$PROJECT_PATH/tsconfig.json"
```

Ensure it includes:
- `"jsx": "react"` or `"jsx": "preserve"`
- Proper module resolution settings

### Step 11: Generate Summary

Provide a summary of the implementation:

```markdown
## Template Set Implementation Summary

### Project
- Project path: $PROJECT_PATH
- Layout file: $LAYOUT_FILE

### Resources Added
- CSS files: X resources added to Layout
- JavaScript files: Y resources added to Layout
- Total resources: Z

### Changes Made
- ✓ Required imports added/verified
- ✓ CSS resources inserted in <head>
- ✓ JavaScript resources inserted in <head>
- ✓ Body structure matched to source HTML
- ✓ Main content wrapper preserved
- ✓ Comments added for organization
- ✓ Absolute areas added to Layout.tsx (header/footer via AbsoluteArea)
- ✓ Multiple page templates created (basic, home, landing, etc.)
- ✓ MainResource template created (if needsFullPage components exist)

### File Structure
Layout file now includes:
1. Imports from @jahia/javascript-modules-library
2. CSS resources (loaded first)
3. JavaScript resources (loaded after CSS)
4. Body structure matching source HTML (classes, IDs, wrappers)

### Next Steps
1. Review the Layout file: `$LAYOUT_FILE`
2. Reorder resources if specific load order is required
3. Build the project: `cd $PROJECT_PATH && yarn build`
4. Deploy to Jahia: `cd $PROJECT_PATH && yarn deploy`
5. Test the template in Jahia to ensure all assets load correctly

### Resource URLs
After deployment, resources will be accessible at:
- CSS: `/modules/[projectname]/css/[projectname]/[filename].css`
- JS: `/modules/[projectname]/js/[projectname]/[filename].js`

### Troubleshooting
- If assets don't load, verify `package.json` has correct static-resources configuration
- If build fails, check for TypeScript syntax errors in Layout file
- If styles don't apply, check browser console for 404 errors
```

### Step N: Create Multiple Page Templates

A Jahia module can have multiple page templates for different page layouts. Each template is a separate file in `src/templates/Page/`.

**Read the manifest for template variants:**
```bash
jq '.templateVariants' workflow-output/component-manifest.json 2>/dev/null
```

**For each variant, create `src/templates/Page/{name}.server.tsx`:**

```tsx
// src/templates/Page/basic.server.tsx — standard interior page
import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "~/templates/Layout";

jahiaComponent(
  { nodeType: "jnt:page", name: "basic", componentType: "template" },
  () => (
    <Layout>
      <Area name="main" />
    </Layout>
  )
);
```

```tsx
// src/templates/Page/home.server.tsx — home page with distinct structure
import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "~/templates/Layout";

jahiaComponent(
  { nodeType: "jnt:page", name: "home", componentType: "template" },
  () => (
    <Layout>
      <Area name="main" />
    </Layout>
  )
);
```

```tsx
// src/templates/Page/landing.server.tsx — landing page (no nav, minimal header)
import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "~/templates/Layout";

jahiaComponent(
  { nodeType: "jnt:page", name: "landing", componentType: "template" },
  () => (
    // Landing pages often skip the shared header/footer
    <Layout showHeader={false} showFooter={false}>
      <Area name="main" />
    </Layout>
  )
);
```

**Rules:**
- The `name` field in `jahiaComponent` is what appears in the Jahia "Template" dropdown when creating a page
- Every project MUST have at minimum a `basic` template
- No CND changes needed — `jnt:page` is a core Jahia type
- The `home` template is typically identical to `basic` but can differ in available area types or layout structure

### Step N+1: Create the MainResource Template

If any component is flagged `"needsFullPage": true` in the manifest, create `src/templates/MainResource/default.server.tsx`:

```tsx
import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "~/templates/Layout";

jahiaComponent(
  {
    nodeType: "jmix:mainResource",
    name: "default",
    componentType: "template",
  },
  (_, { currentNode }) => (
    <Layout>
      <Render node={currentNode as JCRNodeWrapper} view="fullPage" />
    </Layout>
  )
);
```

**How it works:**
- This template is a universal router for ALL `jmix:mainResource` content types
- When a news article's URL is visited, Jahia selects this template
- It wraps the node in the shared `Layout` (header, footer, etc.)
- `<Render view="fullPage" />` delegates to the component's own `fullPage.server.tsx`
- Every content type with `jmix:mainResource` MUST have a `fullPage` view (created by `/implement-components`)

## Important Notes

1. **Body Structure Matching** ⚠️ CRITICAL: The Layout body structure MUST match the source HTML exactly. CSS selectors and JavaScript rely on specific class names, IDs, and DOM structure. Failing to match the structure will result in broken styles and functionality.

2. **File Backup**: Consider backing up the Layout file before making changes (especially if it has custom content)

3. **Load Order**: JavaScript files may have dependencies. Common patterns:
   - jQuery should load before jQuery plugins
   - Framework files should load before application code
   - Vendor files should load before custom code

4. **File Naming**: Files with parentheses in names (e.g., `optimized-min(1).css`) need special handling in URLs

5. **Performance**: Loading many individual files can impact performance. Consider:
   - Combining files in production
   - Using async/defer for non-critical JS
   - Conditionally loading resources based on page type

6. **TypeScript vs JavaScript**: If the Layout file is `.tsx`, ensure proper TypeScript types are used. If it's `.jsx`, the syntax is the same but without type annotations.

7. **Comments**: Use helpful comments to organize resources by category (e.g., vendor files, theme files, component files)

## Error Handling

- **No JS project found**: Inform user and ask for manual project path
- **No Layout file found**: Offer to create a new one or specify path
- **No static files found**: Warn that `/import-website-assets` should be run first
- **No source HTML found**: Ask user to provide path to original HTML file, or skip body structure matching
- **Invalid body structure**: If source HTML structure is unclear, use default `<body>{children}</body>` and warn user
- **Invalid Layout syntax**: Warn user and suggest manual review before proceeding
- **TypeScript errors**: Note that build will catch these, user can fix manually
- **Edit fails**: Provide the generated code so user can manually add it

## Usage Examples

**Basic usage (after importing assets):**
```bash
/implement-template-set
```

**With specific project:**
```bash
/implement-template-set ./addemo
```

**Rerun after importing more assets:**
```bash
# Import additional assets
/import-website-assets https://example.com

# Update template set with new assets (use merge mode)
/implement-template-set
```

## Integration with Workflow

This command fits into the complete Jahia workflow:

1. `/analyze-website` - Analyze target website and identify components
2. `/import-website-assets` - Download and import CSS, JS, and assets
3. **`/implement-template-set`** ← This command (configure Layout to use imported assets)
4. `/implement-components` - Implement Jahia components
5. `/create-content` - Create pages and content via GraphQL

ARGUMENTS: [project-path] (optional - will auto-detect if not provided)
