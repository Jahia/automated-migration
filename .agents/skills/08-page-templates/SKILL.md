---
name: 8-page-templates
description: Implement Layout.tsx with AbsoluteArea, page template variants (basic, home, landing), and MainResource template. Use after asset import and before component implementation.
type: production
phase: 8
status: active
depends_on:
  - 3-import-assets
allowed-tools: Bash, Read, Write, Edit
---

## Agent identity
- **Agent name:** Templeron
- **Reference style:** Blueprint / drafting
- **Signature line (en):** *"The canvas before the paint."*
- **Personality note:** Focused on the Layout shell and AbsoluteArea placement. Does not implement component logic — that belongs to Parallex.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---


## Template architecture (home vs inner) — REQUIRED

Real sites have at least TWO page templates, plus shared shell:
- **Layout.tsx**: AbsoluteAreas for the shared **top-bar, navigation, footer** (parent = home page node). Shared regions are AbsoluteAreas, never hardcoded or <Render>ed inside another component.
- **home.server.tsx** (template name `home`): the home page — leads with hero/carousel; content in an editable `<Area name="main"/>`. Assign the home page to it (`j:templateName=home`).
- **basic.server.tsx** (template name `basic`, every inner page): renders, in order, the **page banner title** (page `jcr:title` + an editable per-page banner image, e.g. `nsMix:pageMedia#bannerImage`) → a **breadcrumb** derived from the page hierarchy (walk parents up to home) → the editable `<Area name="main"/>`. This mirrors how almost every CMS site structures inner pages (banner + breadcrumb + content) and is what editors expect.
- **MainResource/default.server.tsx**: full-page detail (`jmix:mainResource`, priority -1) rendering `<Render view="fullPage"/>` inside Layout.

A single bare `<Area main/>` template used for every page (no home template, no banner, no breadcrumb) is WRONG and reads as an unfinished migration. Validate in jContent that the banner/breadcrumb render and the main area is editable.

## Overview

A **page template** defines the full layout of a page. It is registered with `componentType: "template"` and always targets `jnt:page`. Templates contain **Areas** (per-page content) and **AbsoluteAreas** (shared across all pages, e.g. footer, navbar).

---

> ⚠️ **CMS rule — never hardcode links in templates.** Navigation links, logo hrefs, footer links — all must come from contributed content (via props, `buildNodeUrl`, or `j:linkType`). Do not put literal URLs in template code.

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

## Step 1 — Create Layout.tsx (the shared page shell)

`Layout.tsx` wraps every page template. It renders the full HTML document, loads CSS, and places `AbsoluteArea` for the shared header and footer. **AbsoluteArea calls MUST live in Layout.tsx**, not in individual template files.

```tsx
// src/templates/Layout.tsx
import {
  AbsoluteArea,
  AddResources,
  buildModuleFileUrl,
  buildNodeUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ReactNode } from "react";

export const Layout = ({ title, children }: { title?: string; children: ReactNode }) => {
  const { currentResource, renderContext } = useServerContext();
  const lang = currentResource.getLocale().getLanguage();

  // AbsoluteArea parent MUST be the home page node — NOT renderContext.getSite()
  // Content lives at /sites/{siteKey}/home/header and /sites/{siteKey}/home/footer
  const site = renderContext.getSite() as unknown as JCRNodeWrapper;
  const homePage = site.getNode("home") as JCRNodeWrapper;

  // --- Theming: optional site-node overrides (mixin <ns>mix:siteTheme) ---
  // Each set property overrides the matching :root token from theme-tokens.css,
  // letting an editor re-theme the whole site from the site node — no redeploy.
  const overrides: string[] = [];
  const push = (prop: string, cssVar: string) => {
    if (site.hasProperty(prop)) overrides.push(`${cssVar}:${site.getProperty(prop).getString()}`);
  };
  push("themePrimaryColor", "--color-primary");
  push("themeSecondaryColor", "--color-secondary");
  push("themeAccentColor", "--color-accent");
  push("themeTextColor", "--color-text");
  push("themeBackgroundColor", "--color-bg");
  push("themeFontHeading", "--font-heading");
  push("themeFontBody", "--font-body");
  let overrideCssUrl: string | undefined;
  if (site.hasProperty("themeOverrideCss")) {
    try { overrideCssUrl = buildNodeUrl(site.getProperty("themeOverrideCss").getNode()); } catch { /* missing ref */ }
  }

  return (
    <html lang={lang}>
      <head>
        <meta charSet="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>{title ?? "My Site"}</title>
        {/* Order matters: 1) token defaults, 2) base styles that consume var(--token) */}
        <AddResources type="css" resources={buildModuleFileUrl("static/css/theme-tokens.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("dist/assets/style.css")} />
        {/* 3) site-node token overrides — only the props the editor set */}
        {overrides.length > 0 && (
          <style dangerouslySetInnerHTML={{ __html: `:root{${overrides.join(";")}}` }} />
        )}
        {/* 4) uploaded override stylesheet — linked LAST so its rules win */}
        {overrideCssUrl && <link rel="stylesheet" href={overrideCssUrl} />}
      </head>
      <body>
        <AbsoluteArea name="header" nodeType="namespace:mainNavigation" parent={homePage} readOnly="children" />
        {/* Page content MUST be wrapped in <main> — it is the a11y main landmark AND
            what the content.sh gate measures (it counts text inside <main>). Without
            it every page reads as 0 chars even when fully populated. */}
        <main id="main-content">{children}</main>
        <AbsoluteArea name="footer" nodeType="namespace:footer" parent={homePage} readOnly="children" />
      </body>
    </html>
  );
};
```

**Critical rules:**
- **Theme tokens load first, overrides last.** The cascade is: `theme-tokens.css` (`:root` defaults) → bundled CSS that uses `var(--token)` → inline `:root{}` from the site-node mixin → uploaded override stylesheet. Later sources win, so a site can be re-themed without a redeploy. The token layer is produced by skill 03 (`tokenize-css.py`); never hardcode colors/fonts back into component CSS.
- The site-theme props come from the `<ns>mix:siteTheme` mixin added to the **site node** (`/sites/<siteKey>`). Guard every read with `site.hasProperty(...)` — the mixin/props may be absent.
- Import `useServerContext` from `@jahia/javascript-modules-library` — never receive `renderContext` as a template argument
- `AbsoluteArea parent` = `site.getNode("home")` — NOT `renderContext.getSite()`. If you use `getSite()` as parent, the absolute area content is stored at the site root node instead of `/home/header`, which is wrong
- `readOnly="children"` prevents editing the shared header/footer from every inner page — editors can only edit them from the home page
- Use `.js` import extension (not `.jsx`) when importing Layout in template files: `import { Layout } from "../Layout.js"`

---

### Analytics and tracking scripts

Most client sites use Google Tag Manager, GA4, or a cookie consent manager. These must be added to `Layout.tsx` but **suppressed in edit mode** — jcontent fires page events on every toolbar click, which pollutes analytics data and triggers false conversions.

#### Step: Ask the user before implementing

```
Does this site use analytics or tag management?
  1. Google Tag Manager (GTM) — provide the GTM-XXXXXX container ID
  2. Google Analytics 4 (GA4) — provide the G-XXXXXXXXXX measurement ID
  3. Custom script — paste the script tag
  4. None / handled externally
```

#### GTM implementation pattern

```tsx
// In Layout.tsx — import renderContext at the top
import { useServerContext } from "@jahia/javascript-modules-library";

// Inside the Layout component:
const { renderContext } = useServerContext();
const isEditMode = renderContext?.isEditMode() ?? false;
const GTM_ID = "GTM-XXXXXX"; // replace with actual ID

// In the <head> section:
{!isEditMode && (
  <>
    {/* GTM script — only in live mode */}
    <script dangerouslySetInnerHTML={{ __html: `
      (function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
      new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
      j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
      'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
      })(window,document,'script','dataLayer','${GTM_ID}');
    `}} />
  </>
)}

// Immediately after the opening <body> tag (or Layout wrapper div):
{!isEditMode && (
  <noscript>
    <iframe
      src={`https://www.googletagmanager.com/ns.html?id=${GTM_ID}`}
      height="0" width="0"
      style={{ display: "none", visibility: "hidden" }}
    />
  </noscript>
)}
```

#### GA4 direct implementation pattern (no GTM)

```tsx
{!isEditMode && (
  <>
    <script async src={`https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX`} />
    <script dangerouslySetInnerHTML={{ __html: `
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-XXXXXXXXXX');
    `}} />
  </>
)}
```

#### Cookie consent manager

If the site uses a consent manager (OneTrust, Axeptio, Cookiebot, Didomi), add its script the same way — wrapped in `{!isEditMode && ...}`. The consent manager script tag typically goes BEFORE the GTM script so it can block GTM until consent is given.

#### Critical rules

- **Always guard with `!isEditMode`** — no exceptions. Analytics firing in jcontent editor is not recoverable without manually clearing the GTM/GA4 data layer.
- **Never hardcode tracking IDs** — add them as CND properties on a singleton `ns:siteSettings` node (or read from `contextJsParameters` if available) so editors can change them without a code deploy.
- **`dangerouslySetInnerHTML` is acceptable here** — inline tracking scripts cannot be loaded as external modules due to the way GTM works. This is the standard React pattern for analytics.
- **Test in live workspace** only — navigate to `$JAHIA_URL/cms/render/live/fr/sites/$JAHIA_SITE_KEY/home.html` and verify the GTM debug panel shows page view events. Never test from the default workspace render URL.

---

## Step 2 — Create page template files

Each template lives in its own subdirectory with `default.server.tsx`. Import Layout with `.js` extension.

```tsx
// src/templates/HomePage/default.server.tsx
import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jnt:page",
    name: "homePage",
    displayName: "Home page",
  },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    <Layout title={title}>
      <main>
        <Area name="hero" />
        <Area name="main" />
      </main>
    </Layout>
  ),
);
```

**DO NOT** pass `renderContext` as a second argument to page templates just to access `getSite()`. Use `useServerContext()` inside Layout instead.

---

## Step 3 — Create the MainResource template

For modules that have `jmix:mainResource` content types (news articles, events, etc.):

```tsx
// src/templates/MainResource/default.server.tsx
import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.js";

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jmix:mainResource",  // NOT jnt:page
    priority: -1,                    // low priority lets specific types override
  },
  ({ "jcr:title": title }: { "jcr:title"?: string }, { currentNode }) => (
    <Layout title={title}>
      <main>
        <Render node={currentNode as JCRNodeWrapper} view="fullPage" />
      </main>
    </Layout>
  ),
);
```

**Common mistake:** using `nodeType: "jnt:page"` with `name: "mainResource"` — this creates a selectable page template named "mainResource" instead of a fallback for content nodes.

### MainResource/default.server.tsx — canonical pattern

```tsx
// CORRECT — Layout once, renders fullPage view
export default function MainResourceTemplate({ currentNode, renderContext }: Props) {
  const title = currentNode.hasProperty("jcr:title")
    ? currentNode.getProperty("jcr:title").getString()
    : currentNode.getName();
  return (
    <Layout title={title}>
      <main>
        <Render node={currentNode as JCRNodeWrapper} view="fullPage" />
      </main>
    </Layout>
  );
}
```

**Never do this:**
- Add a second `<Layout>` inside `fullPage.server.tsx`
- Add `<AbsoluteArea name="header">` or `<AbsoluteArea name="footer">` inside `fullPage.server.tsx`
- Include navigation components inside fullPage views

The `fullPage.server.tsx` view renders ONLY the article-level content body (title, image, body text, tags, date, related items). `<Layout>` is provided exactly once by the MainResource template wrapper.

---

## Step 4 — Choose: Area vs AbsoluteArea

| | `<Area>` | `<AbsoluteArea>` |
|---|---|---|
| Content | Per-page (each page has its own) | Shared across all pages |
| Use for | Page body, hero, sections | Header, footer, global sidebar |
| Where to put it | In template files | **In Layout.tsx only** |
| `parent` prop | Not needed | `site.getNode("home")` from `useServerContext()` |

---

## Step 3 — Use typed area nodes (required for good editorial UX)

Instead of a single generic area type, define **one area type per section** with a tight child constraint. This ensures editors only see relevant content types in each area's "New content" menu.

```cnd
// settings/definitions.cnd

[namespacemix:pageComponent] > namespacemix:component mixin

// ✅ Typed areas — editors only see the right types per area
// Use jmix:hiddenType (NOT jmix:studioOnly) — hides from picker while keeping rendering intact
[namespace:heroArea] > jnt:content, jmix:list, jmix:hiddenType orderable
 + * (namespace:heroSection)

[namespace:featuresArea] > jnt:content, jmix:list, jmix:hiddenType orderable
 + * (namespace:featureCard)

// Generic fallback — use only when no tighter constraint makes sense
[namespace:pageArea] > jnt:content, jmix:list, jmix:hiddenType orderable
 + * (namespacemix:pageComponent)
```

Then in the template:

```tsx
<Area name="hero"     nodeType="namespace:heroArea" />
<Area name="features" nodeType="namespace:featuresArea" />
<Area name="footer"   nodeType="namespace:pageArea" />   // generic ok for footer
```

> ⚠️ **Never use a generic `pageArea` for every area.** If all areas accept all `pageComponent` types, editors will see "New Hero Section" as an option in a feature card area, which is confusing and error-prone.

> **Sections driven by content folders** (e.g. a tutorials listing that queries `/contents/tutorials/`) should NOT use an Area at all — the template renders them via a server-side query component. Exposing an Area there invites editors to manually add duplicates of auto-queried content.

> ⚠️ **CSS gotcha — `Area` renders children directly, no wrapper div.** When wrapping an `<Area>` in a container div and styling children with `.container > div { display: grid }`, the grid won't apply because there is no intermediate `div` — the area's child components are rendered as direct children of `.container`. Always apply grid/flex layout **on the container itself** when its only content is an Area:
> ```css
> /* ✅ correct — grid on the container that wraps the Area */
> .featuresSection .container { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1.5rem; }
> /* ❌ wrong — no div is inserted between container and the card articles */
> .container > div { display: grid; }
> ```

### ⚠️ After defining `pageComponent` — update existing components

**This is the most common mistake:** if the module already has content types, they all extend `namespacemix:component`. After introducing the custom area type, **editors will not be able to drop anything** until you update the page-level components to extend `namespacemix:pageComponent` instead.

Scan all `definition.cnd` files and update every component that should be droppable in page areas:

```cnd
// Before (editors can't drop in pageArea):
[namespace:heroSection] > jnt:content, namespacemix:component

// After (editors can drop in pageArea):
[namespace:heroSection] > jnt:content, namespacemix:pageComponent
```

**Which components need `pageComponent`?**
- Standalone page sections (hero, feature cards, text blocks, etc.) → `namespacemix:pageComponent`
- Child-only types (CTA inside hero, card inside list) → keep `namespacemix:component`
- `jmix:mainResource` types stored in content folders → keep `namespacemix:component`

---

## Step 4 — Page template vs sectioning component

Before creating a new page template, ask:

| Is this… | Use a… |
|---|---|
| A new top-level page layout (different column structure, hero slot) | **New page template** |
| A layout variation that could be reused as a section on any page | **Sectioning component** (use the build-component skill) |
| A minor style difference on an existing template | **Named view** of the existing template |

**Guideline**: keep page templates small (1–4). Use sectioning components for compositional differences.

---

## Step 5 — Define structural (non-selectable) container nodes

Some nodes are purely structural — they hold child nodes but shouldn't appear in the component picker. Omit `namespacemix:component` and add `jmix:hiddenType`:

```cnd
[namespace:header] > jnt:content, jmix:hiddenType
 + hero (namespace:heroSection)
```

Render it with `RenderChild`:

```tsx
// src/components/Header/default.server.tsx
import { jahiaComponent, RenderChild } from "@jahia/javascript-modules-library";

jahiaComponent(
  { componentType: "view", nodeType: "namespace:header" },
  () => <RenderChild name="hero" />,
);
```

---

## Step 6 — Bootstrap site structure with import.xml

`import.xml` provisions every new site created from this template set. **Always update it** — editors cannot contribute if there's no page structure to start from.

**Minimum required:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<content xmlns:j="http://www.jahia.org/jahia/1.0" xmlns:jcr="http://www.jcp.org/jcr/1.0">
  <modules jcr:primaryType="jnt:modules">
    <your-module-name>

      <!-- Homepage — MUST use your actual template name, not "basic" -->
      <home j:isHomePage="true" j:templateName="homepage" jcr:primaryType="jnt:page">
        <j:translation_en jcr:language="en" jcr:mixinTypes="mix:title"
          jcr:primaryType="jnt:translation" jcr:title="Home"/>

        <!-- Pre-create area nodes so editors can start dropping content immediately -->
        <hero jcr:primaryType="namespace:pageArea"/>
        <main jcr:primaryType="namespace:pageArea"/>
      </home>

      <!-- Add sub-pages for each template you created -->
      <documentation j:templateName="documentation" jcr:primaryType="jnt:page">
        <j:translation_en jcr:language="en" jcr:mixinTypes="mix:title"
          jcr:primaryType="jnt:translation" jcr:title="Documentation"/>
        <hero jcr:primaryType="namespace:pageArea"/>
      </documentation>

      <!-- Offline management pages — never published, system-name locked -->
      <drafts jcr:primaryType="jnt:page" j:templateName="basic"
        jcr:mixinTypes="jmix:systemNameReadonly jmix:nolive">
        <j:translation_en jcr:language="en" jcr:mixinTypes="mix:title"
          jcr:primaryType="jnt:translation" jcr:title="Drafts"/>
      </drafts>

      <!-- Content folders — store jmix:mainResource content here, not in pages -->
      <contents jcr:primaryType="jnt:contentFolder">
        <articles jcr:primaryType="jnt:contentFolder"
          jcr:mixinTypes="jmix:contributeMode" j:contributeTypes="namespace:docArticle">
          <j:translation_en jcr:language="en" jcr:primaryType="jnt:translation" jcr:title="Articles"/>
        </articles>
      </contents>

    </your-module-name>
  </modules>
</content>
```

**Rules:**
- `j:templateName` must match the `name:` in your `jahiaComponent` call — if it's wrong, editors get a blank page
- Pre-create area nodes (`jcr:primaryType="namespace:pageArea"`) so editors don't face empty containers on first open
- Add a starter component in the hero area so the page isn't visually blank (optional but strongly recommended)
- Content folders with `jmix:contributeMode` + `j:contributeTypes` restrict what editors can create in them
- `jmix:systemNameReadonly` prevents editors from renaming or moving management pages; `jmix:nolive` prevents accidental publishing

---

## Step 7 — Build and deploy

```bash
yarn build && yarn jahia-deploy
```

> ⚠️ **Do not use `yarn dev`** — it is a continuous file watcher that should only be started manually when needed for rapid iteration. For agentic workflows, always use `yarn build && yarn jahia-deploy` for explicit, one-shot deploys.

After deploying, the new template will appear in the **template selection** step when creating a new page (right-click on a page in the sidebar → **+ New Page**).

---

## Common patterns

### Single column with shared footer

```tsx
<Layout title={title}>
  <Area name="main" />
  <AbsoluteArea name="footer" parent={renderContext.getSite()} nodeType="namespace:footer" />
</Layout>
```

### Two-column layout

```tsx
<Layout title={title}>
  <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "2rem" }}>
    <Area name="sidebar" />
    <Area name="main" />
  </div>
</Layout>
```

### Edit mode-aware rendering

```tsx
({ "jcr:title": title }, { renderContext }) => {
  const isEdit = renderContext.isEditMode();
  return (
    <Layout title={title}>
      <Area name="main" />
      <nav style={{ flexDirection: isEdit ? "column" : "row" }}>
        <AbsoluteArea name="footer" parent={renderContext.getSite()} />
      </nav>
    </Layout>
  );
}
```

---

## Validation checklist
- [ ] File is in `src/templates/Page/`
- [ ] `componentType: "template"` and `nodeType: "jnt:page"`
- [ ] `name` is set (used in Jahia UI template picker)
- [ ] Areas use a custom area node type (not bare `<Area name="..."/>`)
- [ ] Custom area type has `jmix:list`, `jmix:hiddenType`, and `orderable`
- [ ] `AbsoluteArea` uses `renderContext.getSite()` as parent
- [ ] Structural container nodes use `jmix:hiddenType` (hidden from picker)
- [ ] Decision made: page template vs sectioning component (see Step 4)
- [ ] `yarn build && yarn jahia-deploy` run and template appears in Jahia UI

## Troubleshooting

### Area renders blank — content invisible

**Symptom:** An Area in your template produces no HTML output at all, even though you can see children in jContent.

**Root cause:** Jahia's `Area` component auto-creates the JCR area node using its declared `nodeType` on first page load. If that node was subsequently **deleted and recreated manually** (e.g. via GraphQL) with a *different* type, the declared type and the actual JCR type no longer match — and Jahia silently renders nothing.

**Fix:** Delete the mistyped node and let Jahia recreate it automatically:

```graphql
mutation {
  jcr {
    mutateNode(pathOrId: "/sites/mySite/home/hero") {
      delete
    }
  }
}
```

Visit the page — Jahia recreates the node with the correct type and children render again.

**Prevention:** Never manually create area nodes via GraphQL with a type that differs from the `nodeType` declared in the template. Always let Jahia auto-create area nodes on first render.

> https://academy.jahia.com/tutorials-get-started/front-end-developer/the-about-us-page
