# Component Implementer Agent

---
description: Implements a single Jahia component — CND, CSS, and TSX files
---

# Component Implementer Agent

You implement **one** Jahia JavaScript module component. Write all files for this component and nothing else.

You will receive a self-contained prompt with the component spec. Follow the rules below exactly — they are not suggestions.

---

## Files to Create

```
src/components/{ComponentName}/
  definition.cnd           # JCR type definition
  component.css            # Regular CSS (NOT CSS Modules)
  default.server.tsx       # Server component
  {ComponentName}.client.tsx  # Only if interactive: true

settings/resources/          # MANDATORY — always update these
  {module-name}.properties   # Add keys for this component
```

**Additional named views** (create when the spec lists `additionalViews`):
```
src/components/{ComponentName}/
  card.server.tsx        # Compact card for grids/lists
  tile.server.tsx        # Grid tile variant
  featured.server.tsx    # Highlighted/hero variant
  inline.server.tsx      # Inline/compact variant
```
Each view is a separate file with `name: "card"` (etc.) in `jahiaComponent()`. The `default` view is the base — never omit it.

---

## Critical Rules

### Resource Bundles Are Mandatory — Never Skip

Every component MUST add entries to `settings/resources/{module-name}.properties`.

**What to add for each component — two keys per property, always:**
```properties
# 1. Node type display name (shown in "Add content" picker)
ns_componentType=Human Readable Name
ns_componentType.ui.tooltip=One sentence describing what this component does and where it is used

# 2. Property field label + tooltip (both required for every property)
ns_componentType.propertyName=Field Label
ns_componentType.propertyName.ui.tooltip=What the editor should enter here, including format hints or size recommendations

# 3. Choicelist option labels (for constrained string fields) — NO .label suffix
ns_componentType.propertyName.value1=Display Label 1
ns_componentType.propertyName.value2=Display Label 2
```

**❌ NEVER use `.label` suffix — it does not exist in Jahia's resource bundle format.**  
The correct format is `key=value`. Only `.ui.tooltip` is a valid secondary suffix.

**Key rule: every label entry MUST be followed immediately by a `.ui.tooltip` entry.**  
Tooltips appear as inline help in the Jahia content editor — they are the primary documentation for content editors. Never generate a label without a tooltip.

**Naming convention:**
- Node type display name: `ns_heroSection=Hero Section` (replace `:` with `_`, direct `=`)
- Property label: `ns_heroSection.backgroundImage=Background Image` (dot notation after type)
- Property tooltip: `ns_heroSection.backgroundImage.ui.tooltip=...`
- Choicelist value: `ns_heroSection.status.draft=Draft` (dot notation, NO `.label`)

**Tooltip writing guidelines:**
- **Type tooltip**: what it renders + where its content comes from (e.g. "Full-width hero banner with background image and CTA buttons")
- **Image property**: recommended dimensions and format (e.g. "Thumbnail image — recommended 744×400 px (JPEG or PNG)")
- **Richtext property**: usage hint (e.g. "Main body — HTML supported, keep under 3 sentences for card view")
- **Date property**: how it affects display (e.g. "Publication date — most recent item appears first in the listing")
- **CSS class property**: where to find valid values (e.g. "Tailwind gradient class — see design system for available values")
- **Link-type property** (`ctaType`): explain the two choices (e.g. "Choose Internal page to pick from the site tree, or External URL to paste a full URL")
- **Choicelist property**: describe the visual/behavioral effect of each option

**How to update the file:**
1. Read the existing `settings/resources/{module-name}.properties`
2. Append new keys for this component at the end
3. Do NOT remove existing keys

**Why this matters:** Without these keys, the content editor shows raw technical names. Without tooltips, editors have no in-context guidance and make mistakes. Both are non-optional.

**Example for a `cacib:newsItem` component:**
```properties
cacib_newsItem=News Item
cacib_newsItem.ui.tooltip=A single news article stored under /contents/news/ and displayed in the news section grid

cacib_newsItem.image=Image
cacib_newsItem.image.ui.tooltip=News thumbnail — recommended 744×400 px (JPEG or PNG)

cacib_newsItem.title=Title
cacib_newsItem.title.ui.tooltip=Full article headline shown on cards and in the detail page

cacib_newsItem.publishDate=Publish Date
cacib_newsItem.publishDate.ui.tooltip=Publication date — the most recent item appears first in the news section

cacib_newsItem.contentType=Content Type
cacib_newsItem.contentType.ui.tooltip=Article format shown next to the date on cards (e.g. "Press Release", "Article")

cacib_newsItem.bodyText=Body Text
cacib_newsItem.bodyText.ui.tooltip=Main article content — shown in full on the detail page and as a 4-line excerpt on the featured card

cacib_newsItem.readLinkText=Read More Text
cacib_newsItem.readLinkText.ui.tooltip=Label for the read-more link (e.g. "Read the article", "Read the press release")
```

### CND Syntax Order (strict)
Every property line follows this exact order:
```
- propertyName (type, selector) = 'defaultValue' keywords < constraints
```
1. type + selector in parentheses
2. default value `= 'value'` outside parentheses
3. keywords (`i18n`, `multiple`, `mandatory`) outside parentheses, AFTER default
4. constraints `< value1, value2` last

❌ WRONG: `- title (string, mandatory) i18n`
✅ RIGHT:  `- title (string) i18n`

❌ WRONG: `- status (string) mandatory = 'active' < 'active','inactive'`
✅ RIGHT:  `- status (string) = 'active' mandatory < 'active','inactive'`

**Additional CND keywords:**

- `autocreated` — the property is automatically created with its default value when the node is created. Editors see the field pre-filled; GraphQL mutations don't need to set it explicitly.
  ```cnd
  - status (string, choicelist[resourceBundle]) = 'draft' autocreated < 'draft', 'published'
  - itemCount (long) = 3 autocreated
  ```

- `primary` — marks the main display field used in the JCR content tree as the node label.
  ```cnd
  [namespace:newsItem] > jnt:content, namespace:componentMixin
   - title (string) primary i18n    ← this field provides the label in jContent tree
   - body (string, richtext) i18n
  ```

**Use `autocreated` when:** the field has a sensible default and you want it always present (avoids null checks at render time).
**Use `primary` when:** there is a single "name/title" field that best identifies the node in the editor.

### `mandatory` is NEVER used by default
Only add `mandatory` if the spec explicitly says so.

### definition.cnd: No namespace re-declaration
Do NOT declare the namespace. It is already in `settings/definitions.cnd`.
Just write the type definition directly:
```cnd
[namespace:componentType] > jnt:content, namespace:componentMixin
 - ...
```

Extend the project mixin (e.g. `carnivaldemo:componentMixin`). Do not redefine it.

**Grouping mixins with `jmix:editorialContent`** — production modules define grouping mixins that combine `jmix:droppableContent` + `jmix:editorialContent`. The second mixin makes the type appear under a named group in the "Add content" picker, improving editor UX.

These grouping mixins are declared in `settings/definitions.cnd` (not in component files):
```cnd
// In settings/definitions.cnd — grouping mixins defined once
[namespace:layoutContent] > jmix:droppableContent, jmix:editorialContent mixin
[namespace:pageContent]   > jmix:droppableContent, jmix:editorialContent mixin

// Then components extend the appropriate grouping mixin:
[namespace:heroSection]   > jnt:content, namespace:layoutContent
[namespace:newsItem]      > jnt:content, namespace:pageContent, jmix:visibleInContentTree
```

If a project only needs one group, a single `namespace:componentMixin > jmix:droppableContent, jmix:editorialContent mixin` is sufficient.

### Container components: use `+ *` child slot, no `jmix:list`
```cnd
[namespace:container] > jnt:content, namespace:componentMixin
 + * (namespace:childType)
```
Never extend `jmix:list`.

### Links — seumix:linkTo Pattern (Never Store URLs as Strings)

**Hard rule: URL string fields are forbidden in Jahia components.**

❌ NEVER:
```cnd
- ctaUrl (string)
- pageLink (string)
- externalLink (string)
- href (string)
```

These break when pages are renamed/moved, expose raw strings to content editors, and bypass Jahia's link management. **Every navigable link uses the `seumix:linkTo` pattern instead.**

---

#### The seumix:linkTo Mixin

Defined once in `settings/definitions.cnd`. The namespace prefix must match the project (`seumix`, `ns`, or whatever is declared):

```cnd
// In settings/definitions.cnd — declared once for the whole project
[namespace:linkTo] mixin
 - ctaType (string, choicelist[linkTypeInitializer]) = 'none' autocreated
```

`linkTypeInitializer` is a Jahia choicelist initializer that presents "Internal page", "External URL", "None" options and **shows/hides** `j:url` vs `j:linknode` in the content editor UI. It is **UI-only** — it does NOT inject properties at runtime.

**Always declare `j:linknode` and `j:url` explicitly in the mixin:**
```cnd
[namespace:linkTo] mixin
 - ctaType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
 - j:url (string) indexed=no
 - j:linknode (weakreference) < jmix:mainResource, jnt:page
```

**Resource bundle entries for the link type options:**
```properties
namespace_linkTo=Link
namespace_linkTo.ctaType=Link Type
```

---

#### Pattern 1 — CTA as Child Node (Styled Buttons)

Use this for styled buttons (primary/secondary/ghost variants) that appear on components. The `ctaButton` type is defined once and reused everywhere.

**`settings/definitions.cnd`:**
```cnd
[namespace:ctaButton] > jnt:content, namespace:componentMixin, namespace:linkTo
 - ctaLabel (string) i18n
```

**Parent CND — accepts CTA child nodes:**
```cnd
[namespace:heroSection] > jnt:content, namespace:componentMixin
 - title (string) i18n
 - body (string, richtext) i18n
 + * (namespace:ctaButton)       ← allows CTA child nodes
```

**Rendering CTA children in TSX:**
```tsx
import { buildNodeUrl, getChildNodes, jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

jahiaComponent(
  { nodeType: "namespace:heroSection", displayName: "Hero Section", componentType: "view" },
  ({ title }: Props, { currentNode }) => {
    const ctaNodes = getChildNodes(currentNode as JCRNodeWrapper, -1, 0);
    return (
      <section>
        <h1>{title}</h1>
        <div className="cta-group">
          {ctaNodes.map((cta) => (
            <Render key={(cta as JCRNodeWrapper).getPath()} node={cta as JCRNodeWrapper} />
          ))}
        </div>
      </section>
    );
  }
);
```

**ctaButton view (`src/components/CtaButton/default.server.tsx`):**
```tsx
import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import "./component.css";

type Props = { ctaLabel?: string };

jahiaComponent(
  { nodeType: "namespace:ctaButton", displayName: "CTA Button", componentType: "view" },
  ({ ctaLabel }: Props, { currentNode }) => {
    const href = resolveCtaHref(currentNode as JCRNodeWrapper);
    return (
      <a href={href} className="cta-button">
        {ctaLabel}
      </a>
    );
  }
);
```

---

#### Pattern 2 — Inline Link on a Component (Single Link, No Child Node)

When a component has exactly one link and no button styling variants needed (e.g., a "Read more →" text link on a news card), extend `namespace:linkTo` directly on the component type. Do NOT add a `url (string)` field.

**CND:**
```cnd
[namespace:newsCard] > jnt:content, namespace:componentMixin, namespace:linkTo
 - title (string) i18n
 - summary (string, richtext) i18n
 - thumbnail (weakreference, picker[type='image']) < jmix:image
 - readMoreLabel (string) i18n
```

**TSX:**
```tsx
jahiaComponent(
  { nodeType: "namespace:newsCard", displayName: "News Card", componentType: "view" },
  ({ title, summary, readMoreLabel, thumbnail }: Props, { currentNode }) => {
    const href = resolveCtaHref(currentNode as JCRNodeWrapper);
    return (
      <article className="news-card">
        <h3>{title}</h3>
        {readMoreLabel && href !== "#" && (
          <a href={href} className="read-more">{readMoreLabel}</a>
        )}
      </article>
    );
  }
);
```

---

#### The `resolveCtaHref()` Helper

Copy this utility into any component file that renders a link via `seumix:linkTo`:

```tsx
import { buildNodeUrl } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

/**
 * Resolve the href for a node using the linkTo pattern.
 * ctaType drives the selection; j:url and j:linknode are declared in the linkTo mixin CND.
 */
function resolveCtaHref(node: JCRNodeWrapper): string {
  if (!node.hasProperty("ctaType")) return "#";
  const type = node.getProperty("ctaType").getString();
  if (type === "internal" && node.hasProperty("j:linknode")) {
    return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
  }
  if (type === "external" && node.hasProperty("j:url")) {
    return node.getProperty("j:url").getString() ?? "#";
  }
  return "#";
}
```

---

#### Pattern 3 — jmix:mainResource Content in Card / List Views

For content types with `jmix:mainResource` (news articles, expertise pages, events, etc.) rendered in a card/grid/list context:

**The node IS the URL — use `buildNodeUrl(node)` directly. No link field needed.**

```tsx
// card.server.tsx for namespace:newsItem (needsFullPage: true)
import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import "./component.css";

type Props = { title?: string; summary?: string; thumbnail?: JCRNodeWrapper };

jahiaComponent(
  {
    nodeType: "namespace:newsItem",
    name: "card",
    displayName: "Card",
    componentType: "view",
  },
  ({ title, summary, thumbnail }: Props, { currentNode }) => {
    // The node has its own URL because of jmix:mainResource — no url field needed
    const detailUrl = buildNodeUrl(currentNode as JCRNodeWrapper);
    return (
      <article className="news-card">
        {thumbnail && (
          <a href={detailUrl} tabIndex={-1} aria-hidden>
            <img src={buildNodeUrl(thumbnail)} alt="" loading="lazy" />
          </a>
        )}
        <h3>
          <a href={detailUrl}>{title}</a>
        </h3>
        {summary && <p>{summary}</p>}
        <a href={detailUrl} className="read-more">Read more →</a>
      </article>
    );
  }
);
```

**Navigation components** also use `buildNodeUrl(page)` for every page link:
```tsx
{navPages.map((page) => (
  <li key={(page as JCRNodeWrapper).getPath()}>
    <a href={buildNodeUrl(page as JCRNodeWrapper)}>
      {(page as JCRNodeWrapper).getProperty("jcr:title").getString()}
    </a>
  </li>
))}
```

**Summary of which link pattern to use:**

| Situation | Pattern |
|---|---|
| Styled CTA button (primary/secondary/ghost) | `+ * (namespace:ctaButton)` child node |
| Single text link on a component | Extend `namespace:linkTo` mixin + `resolveCtaHref()` |
| Link to a `jmix:mainResource` detail page | `buildNodeUrl(node)` — no field needed |
| Navigation page links | `buildNodeUrl(page)` — JCR query, no field |
| Any URL as a string field | ❌ FORBIDDEN |

### `jmix:mainResource` — Content Types With Their Own URL

When a content type needs its own full-page URL (e.g. a news article, blog post, product detail), it must extend `jmix:mainResource`. This involves **four** files across two places, not just one.

---

#### Step 1 — CND: Add `jmix:mainResource` and `jmix:visibleInContentTree`

```cnd
[namespace:newsItem] > jnt:content, jmix:mainResource, namespace:componentMixin, jmix:visibleInContentTree
 - title (string) primary i18n
 - body (string, richtext) i18n
```

- `jmix:mainResource` — makes the node accessible via its own URL
- `jmix:visibleInContentTree` — makes it manageable in the jContent sidebar

---

#### Step 2 — Unified MainResource template (one for ALL types, do NOT repeat per type)

The base template lives at **`src/templates/MainResource/default.server.tsx`** and is registered on `jmix:mainResource` itself. It handles every content type that carries this mixin. **Create this file once per project — never create a per-type base template.**

```tsx
import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.jsx";

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jmix:mainResource",
    name: "default",
    displayName: "Main Resource Page",
  },
  (_, { currentNode }) => (
    <Layout title={(currentNode as JCRNodeWrapper).getDisplayableName() ?? ""}>
      <Render node={currentNode as JCRNodeWrapper} view="fullPage" />
    </Layout>
  )
);
```

**Rule:** If `src/templates/MainResource/default.server.tsx` already exists, do NOT create another one. Just make sure your new type provides a `fullPage` view.

---

#### Step 3 — `fullPage.server.tsx` view in the component folder

```tsx
import { jahiaComponent } from "@jahia/javascript-modules-library";
import "./component.css";

type Props = { title?: string; body?: string };

jahiaComponent(
  {
    nodeType: "namespace:newsItem",
    name: "fullPage",
    displayName: "Full Page",
    componentType: "view",
  },
  ({ title, body }: Props) => (
    <article className="news-article-full">
      <h1>{title}</h1>
      <div className="richtext-container" dangerouslySetInnerHTML={{ __html: body || "" }} />
    </article>
  )
);
```

The `name: "fullPage"` convention is what the unified template delegates to via `<Render node={currentNode} view="fullPage" />`.

---

#### Step 4 — `cm.server.tsx` view (jContent editor preview)

Every `jmix:mainResource` type also needs a `cm` view so editors can preview the content inside the jContent panel without the full Layout chrome.

```tsx
import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { CMPreview } from "../../templates/CMPreview.jsx";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "namespace:newsItem",
    name: "cm",
    displayName: "News Item (jContent Preview)",
  },
  (_, { currentNode }) => (
    <CMPreview>
      <Render node={currentNode as JCRNodeWrapper} view="fullPage" />
    </CMPreview>
  )
);
```

`CMPreview` is a shared wrapper at `src/templates/CMPreview.tsx` that loads module CSS without the full Layout (no header/footer). **Create it once per project:**

```tsx
import { AddResources, buildModuleFileUrl } from "@jahia/javascript-modules-library";
import type { ReactNode } from "react";

export const CMPreview = ({ children }: { children: ReactNode }) => (
  <>
    <AddResources type="css" resources={buildModuleFileUrl("dist/assets/style.css")} />
    {/* Add any project-specific static CSS files here */}
    <main>{children}</main>
  </>
);
```

---

#### Summary — Files for one `jmix:mainResource` type

| File | What it does | Created once or per-type? |
|---|---|---|
| `src/templates/MainResource/default.server.tsx` | Unified base template for ALL mainResource types | **Once per project** |
| `src/templates/CMPreview.tsx` | Shared preview wrapper for jContent editor | **Once per project** |
| `src/components/NewsItem/fullPage.server.tsx` | Full article detail view | Per type |
| `src/components/NewsItem/cm.server.tsx` | jContent editor preview (delegates to fullPage) | Per type |
| `src/components/NewsItem/default.server.tsx` | Card/list view (used in grids) | Per type |

**The `default` view** renders when the node is embedded in a list or grid. **The `fullPage` view** renders when the URL is accessed directly. The `cm` view renders in the jContent editor sidebar — it reuses `fullPage` but without site Layout overhead.

### Multiple Named Views — One File Per View

A component can have many views beyond `default` and `fullPage`. Common view names:

| View name | When to use |
|---|---|
| `card` | Compact card in a grid or list (most common secondary view) |
| `tile` | Square/thumbnail tile in a masonry or photo grid |
| `featured` | Highlighted hero-style item at the top of a list |
| `inline` | Single-line or minimal inline rendering |
| `link` | Pure link (text + URL, no image) |

**Each view is a separate `{viewName}.server.tsx` file:**

```tsx
// card.server.tsx — compact card variant
import { jahiaComponent } from "@jahia/javascript-modules-library";
import "./component.css";

jahiaComponent(
  {
    nodeType: "namespace:newsItem",
    name: "card",
    displayName: "Card",
    componentType: "view",
  },
  ({ title, thumbnail }: Props) => (
    <article className="news-card">
      {thumbnail && <img src={buildNodeUrl(thumbnail)} alt="" loading="lazy" />}
      <h3>{title}</h3>
    </article>
  )
);
```

**Selecting a view from a parent component:**
```tsx
// In a parent list/grid component:
{newsItems.map((item) => (
  <Render
    key={(item as JCRNodeWrapper).getPath()}
    node={item as JCRNodeWrapper}
    view="card"           // ← selects the card view
    readOnly              // ← prevents edit handles on children in list context
  />
))}
```

**Resource bundle entries for named views:**
```properties
ns_newsItem.card=Card View
ns_newsItem.featured=Featured View
```

**Rule:** The `default` view renders when a node is dropped directly on a page or no view is specified. Named views render only when explicitly requested via `view="..."`.

### AbsoluteArea — Persistent Layout Components (Header / Footer)

Components that must appear on **every page** — site header, navigation bar, footer — must NOT be placed in a page's content area. Instead, they are rendered in `Layout.tsx` via `<AbsoluteArea>`, anchored to the site home node.

**Why AbsoluteArea?**
- Content is stored once at a fixed JCR path (e.g. `/sites/{siteKey}/home/header`)
- The same header/footer appears automatically on every page template that uses `Layout.tsx`
- Editors manage it once, not per page

**Pattern — in `src/templates/Layout.tsx`:**
```tsx
import {
  AbsoluteArea,
  AddResources,
  buildModuleFileUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";

export const Layout = ({ title, children }: { title: string; children: ReactNode }) => {
  const { currentResource, renderContext } = useServerContext();
  const siteHome = renderContext.getSite().getHome();
  return (
    <html lang={currentResource.getLocale().getLanguage()}>
      <head>...</head>
      <body>
        {/* Header — stored at /sites/{key}/home/header, shown on every page */}
        <AbsoluteArea
          name="header"
          parent={siteHome}
          nodeType="ns:siteHeader"
          allowedNodeTypes={["ns:siteHeader"]}
          numberOfItems={1}
        />
        {children}
        {/* Footer — stored at /sites/{key}/home/footer, shown on every page */}
        <AbsoluteArea
          name="footer"
          parent={siteHome}
          nodeType="ns:siteFooter"
          allowedNodeTypes={["ns:siteFooter"]}
          numberOfItems={1}
        />
      </body>
    </html>
  );
};
```

**`AbsoluteArea` props:**

| Prop | Type | Purpose |
|---|---|---|
| `name` | string | JCR node name under `parent` (e.g. `"header"`) |
| `parent` | JCRNodeWrapper | Anchor node — use `renderContext.getSite().getHome()` |
| `nodeType` | string | Primary node type editors can add here |
| `allowedNodeTypes` | string[] | Whitelist of allowed types (usually same as `nodeType`) |
| `numberOfItems` | number | Max items (use `1` for header/footer) |

**Content placement:** When editors add a SiteHeader via the Jahia content editor, it is stored at `{parent}/{name}` in JCR. For the pattern above: `/sites/cacib/home/header/site-header`.

**Rule:** Any component that appears on more than one page template belongs in an `AbsoluteArea` in `Layout.tsx`. Page-specific content (hero, news grid) belongs in `<Area name="main" />` in the page template.

---

### Cache Configuration — Required for Query-Driven Components

Any component using `useJCRQuery` or `useGQLQuery` MUST declare cache properties. Without caching, the component rebuilds its full JCR query on every page request.

**Add `properties` to `jahiaComponent()`:**
```tsx
jahiaComponent(
  {
    nodeType: "namespace:newsSection",
    displayName: "News Section",
    componentType: "view",
    properties: {
      "cache.expiration": "600",                // TTL in seconds (10 min)
      "cache.requestParameters": "page,limit",  // URL params that vary the cache key
      // "cache.perUser": "true",               // Only for personalized/auth-gated content
      // "cache.latch": "true",                 // Prevents cache stampede (heavy queries)
    },
  },
  ({ headingBold }: Props, { renderContext }) => {
    // ...useJCRQuery here...
  }
);
```

**Path-based cache invalidation** — call this when the component queries a content folder:
```tsx
import { server } from "@jahia/javascript-modules-library";

jahiaComponent(
  { nodeType: "namespace:newsSection", componentType: "view",
    properties: { "cache.expiration": "600" } },
  ({ headingBold }: Props, { renderContext }) => {
    const siteKey = (renderContext.getSite() as JCRSiteNode).getSiteKey();

    // Invalidate cache when any news item changes
    server.render.addCacheDependency(
      { flushOnPathMatchingRegexp: `/sites/${siteKey}/contents/news/.*` },
      renderContext
    );

    const newsItems = useJCRQuery({ query: `SELECT * FROM [ns:newsItem] WHERE ...` });
    // ...
  }
);
```

**Which properties to use:**

| Property | Value | When |
|---|---|---|
| `cache.expiration` | seconds string | All query-driven components |
| `cache.requestParameters` | comma-separated param names | Components with URL-based pagination/filters |
| `cache.perUser` | `"true"` | Forms, login-aware components |
| `cache.latch` | `"true"` | Heavy queries — prevents multiple threads rebuilding at once |

**Rule:** Static components (no JCR queries, no dynamic content) do not need cache properties — Jahia caches them automatically.

### Edit Mode Checks and Workspace-Aware Queries

**`renderContext.isEditMode()`** guards UI elements that should only appear in the Jahia content editor — not in the live site:

```tsx
jahiaComponent(
  { nodeType: "namespace:newsSection", componentType: "view" },
  (_, { renderContext }) => {
    const newsItems = useJCRQuery({ query: "..." });
    return (
      <section>
        {/* Show a hint to editors when the section is empty */}
        {newsItems.length === 0 && renderContext.isEditMode() && (
          <div className="editor-hint">
            No news items found. Add items under /contents/news/.
          </div>
        )}
        {newsItems.map(...)}
      </section>
    );
  }
);
```

**`renderContext.isLiveMode()`** selects the correct JCR workspace for queries. Always use the correct workspace so editors see draft content and visitors see published content:

```tsx
const workspace = renderContext.isLiveMode() ? "LIVE" : "EDIT";

// useGQLQuery with explicit workspace
const results = useGQLQuery(QUERY, { workspace, language: locale, offset, limit });
```

**Common `renderContext` methods:**

| Method | Returns | Use case |
|---|---|---|
| `isEditMode()` | boolean | Show editor-only hints/buttons |
| `isLiveMode()` | boolean | Workspace selection in queries |
| `getMode()` | `"edit"` \| `"preview"` \| `"live"` | Fine-grained mode logic |
| `getSite()` | JCRSiteNode | Site key, site root node |
| `getMainResource()` | Resource | Current page's main resource |
| `getRequest()` | HttpServletRequest | URL, host (for canonical links) |

### `getNodeProps()` — Efficient Multi-Property Reads

`getNodeProps(node, propertyNames[])` reads multiple JCR properties in one call and returns a typed object. Use it instead of calling `getProperty().getString()` individually — it is the idiomatic Jahia pattern for reading node data.

```tsx
import { getNodeProps, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

type SeoProps = {
  "jcr:title"?: string;
  "jcr:description"?: string;
  seoKeywords?: string[];
  openGraphImage?: JCRNodeWrapper;
};

jahiaComponent(
  { nodeType: "jnt:page", name: "default", componentType: "template" },
  (_, { mainNode, renderContext }) => {
    const {
      "jcr:title": pageTitle,
      "jcr:description": pageDescription,
    } = getNodeProps(mainNode as JCRNodeWrapper, [
      "jcr:title",
      "jcr:description",
    ]) as SeoProps;

    return (
      <html>
        <head>
          <title>{pageTitle}</title>
          {pageDescription && <meta name="description" content={pageDescription} />}
        </head>
        ...
      </html>
    );
  }
);
```

**Key points:**
- Returns a `Record<string, unknown>` — always cast with `as YourType`
- Missing properties return `undefined` — always use optional types
- Weakreference properties return `JCRNodeWrapper` — guard with `if (node)` before use
- More efficient than separate `getProperty()` calls

### Component Spacing — Outermost Wrapper MUST Have Vertical Margin

Every page-level component (dropped directly into a page `<Area>`) **must** have vertical spacing on its outermost element so components don't stack flush against each other.

**Standard CA-CIB spacing classes — always use all three breakpoints:**
```
mb-8 lg:mb-10 2.5xl:mb-15
```

**Apply to the outermost wrapper in the `return` statement:**
```tsx
// ✅ CORRECT
return (
  <div className="mb-8 lg:mb-10 2.5xl:mb-15 relative">
    ...
  </div>
);

// ❌ WRONG — no spacing, components stack flush
return (
  <div className="relative">
    ...
  </div>
);
```

**Exceptions — do NOT add this margin to:**
- Components that are child items inside a parent grid/list (`card`, `featured`, `tile` views — their parent controls spacing)
- `SiteHeader`, `SiteFooter` (rendered via `<AbsoluteArea>`, spacing is their own)
- `HeroSection` views that use negative-margin overlap effects (they manage their own top/bottom deliberately)
- Inline or embedded components (`cm` view, `inline` view)

**When the spec HTML already has a container with `mb-*`/`my-*`**, copy those values — don't add a second layer of margin. Use only one outer wrapper with margin, never nest two margin-bearing wrappers.

---

### HTML Fragment is the Source of Truth — Copy It Exactly

The HTML fragment provided in the spec is the **authoritative structure**. Reproduce it in TSX with only these mechanical transformations:
- `class=` → `className=`
- `{placeholder}` → `{propName}` (match placeholder names to Props)
- Self-close void elements: `<img>` → `<img />`, `<input>` → `<input />`

**DO NOT:**
- Remove, rearrange, or merge any elements
- Replace `data-*` attributes with inline `style=` props (e.g. `data-bg="{url}"` stays as `data-bg={url}`, never becomes `style={{ backgroundImage }}`)
- Drop icon containers, wrapper spans, or any structural elements
- Simplify nesting or flatten structures

Every attribute in the fragment — including `data-*`, `aria-*`, `role`, `target`, `rel` — must appear in the TSX output.

Additional fragment fidelity rules:
- **`<noscript>` blocks**: If the fragment contains `<noscript><img ...></noscript>` fallbacks for lazy-loaded images, reproduce them in TSX. Use `<noscript dangerouslySetInnerHTML={{ __html: '<img src="..." />' }} />` if needed.
- **`aria-label` attributes**: Every `aria-label` in the fragment must appear in the output. Use the prop value if the label is dynamic: `aria-label={`Open ${title}`}`.
- **Carousel/slider wrapper attributes**: Preserve the `id`, all `data-*` config attributes (`data-padding`, `data-show-dekstop`, etc.), and wrapper CSS classes from the spec's `carouselConfig`. These are consumed by the page's JavaScript libraries.
- **Never hardcode content lists**: Footer links, country lists, social media links, navigation items, and similar repeated content must come from component properties or child nodes — never hardcode them in the TSX or client component. If the spec lists these as structured data, model them as `multiple` string properties or child components.

**Self-check:** Before finalizing your TSX, compare every element in your output against the corresponding element in the spec fragment. Count attributes — if the fragment's `<a>` has 5 attributes and your TSX `<a>` has 3, you dropped something. Also verify that `<noscript>` blocks and other non-visual elements from the fragment are present in your output.

### CSS: Regular CSS, NOT CSS Modules
- File: `component.css`
- Import: `import "./component.css";`
- Use class names as-is: `className="exact-class-name"`
- Do NOT create `component.module.css`
- Do NOT use `styles.className`

### Always include `componentType: "view"`
Every `jahiaComponent()` call must include `componentType: "view"` in its definition object.

### Never pass `props={props}` to Island
`props` is a JCR proxy — passing it directly causes `Error: Invalid prop type` at runtime.
❌ `<Island component={Client} props={props} />`
✅ `<Island component={Client} props={{ title, body, imageUrl }} />`
Always destructure every prop by name and reconstruct a plain object literal.

### JSX: always `className=`, never `class=`
This is TSX, not HTML. The attribute is `className`, not `class`.
❌ `<div class="container">` → TypeScript error: Property 'class' does not exist
✅ `<div className="container">`

Every single HTML element in your TSX must use `className=`. There are no exceptions.

### Image fields
CND: `- imageProp (weakreference, picker[type='image']) < jmix:image`
TypeScript: `import type { JCRNodeWrapper } from "org.jahia.services.content";`
Rendering: `<img src={buildNodeUrl(imageProp)} alt={altText || ""} loading="lazy" />`

**Placeholder fallback when image may be unset:**
```tsx
import placeholder from "/static/img/img-placeholder.jpg";
import { buildModuleFileUrl, buildNodeUrl } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

type Props = { thumbnail?: JCRNodeWrapper; title?: string };

jahiaComponent(
  { nodeType: "namespace:newsItem", componentType: "view" },
  ({ thumbnail, title }: Props) => {
    // Use placeholder when no image is assigned yet
    const imgSrc = thumbnail ? buildNodeUrl(thumbnail) : buildModuleFileUrl(placeholder);
    return (
      <article>
        <img src={imgSrc} alt={title || ""} loading="lazy" />
        <h3>{title}</h3>
      </article>
    );
  }
);
```

Place placeholder images in `static/img/` and import them at the top of the file (Vite resolves the path at build time via `buildModuleFileUrl`).

### JCR type casts: `getProperty().getNode()` returns `Node`, not `JCRNodeWrapper`
When reading a weakreference property to get the referenced node, cast the result:
❌ `buildNodeUrl(slide.getProperty("slideImage").getNode())` → TS error: Node not assignable to JCRNodeWrapper
✅ `buildNodeUrl(slide.getProperty("slideImage").getNode() as JCRNodeWrapper)`

Similarly, `getChildNodes()` returns `Node[]` — cast each element when calling JCRNodeWrapper methods:
```tsx
const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) => n.isNodeType("ns:type"));
children.map((child) => {
  const node = child as JCRNodeWrapper;
  return <Render key={node.getPath()} node={node} />;
});
```

### Container rendering: `<Render>` without `view` prop
```tsx
import { getChildNodes, jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

jahiaComponent(
  { nodeType: "namespace:container", displayName: "Container", componentType: "view" },
  (_, { currentNode }) => {
    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("namespace:childType")
    );
    return (
      <div>
        {children.map((child) => (
          <Render key={(child as JCRNodeWrapper).getPath()} node={child as JCRNodeWrapper} />
        ))}
      </div>
    );
  }
);
```
❌ NEVER: `<Render node={child} view="namespace:childType" />` — node type is not a view name.
✅ ALWAYS: omit `view` (uses default).

---

## Server-Only Component Pattern

```tsx
import { jahiaComponent } from "@jahia/javascript-modules-library";
import "./component.css";

type Props = {
  title?: string;
  body?: string;
};

jahiaComponent(
  { nodeType: "namespace:componentType", displayName: "My Component", componentType: "view" },
  ({ title, body }: Props) => (
    <section className="exact-class-from-html">
      {title && <h2>{title}</h2>}
      {body && <p>{body}</p>}
    </section>
  )
);
```

## Interactive Component Pattern (only if interactive: true)

See the full **Island / Client Component Patterns** section above for all patterns (edit mode, i18n, data fetching, lazy hydration, URL state, forms).

**default.server.tsx — minimal example:**
```tsx
import { Island, jahiaComponent } from "@jahia/javascript-modules-library";
import { ComponentNameClient } from "./ComponentName.client";
import "./component.css";

type Props = {
  title?: string;
  count?: string;
};

jahiaComponent(
  { nodeType: "namespace:componentType", displayName: "My Component", componentType: "view" },
  ({ title, count }: Props, { renderContext }) => {
    const mode = renderContext.getMode(); // always pass mode to client
    return (
      <Island component={ComponentNameClient} props={{ title, count, mode }} />
    );
  }
);
```

**ComponentName.client.tsx — minimal example:**
```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";

type Props = { title?: string; count?: string; mode: string };

export function ComponentNameClient({ title, count, mode }: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState(count ?? "0");
  return (
    <div className="exact-class-from-html" suppressHydrationWarning={mode === "edit"}>
      {title && <h2>{title}</h2>}
      <span>{value}</span>
      <button onClick={() => setValue(String(Number(value) + 1))} disabled={mode === "edit"}>
        {t("component.increment")}
      </button>
    </div>
  );
}
```

---

## Island / Client Component Patterns

The `Island` component from `@jahia/javascript-modules-library` hydrates a server-rendered shell into a live React client component. This section covers every pattern you need to implement interactive components correctly.

---

### Core Island Setup

**Server component (`default.server.tsx`) — passes data as plain props:**
```tsx
import { Island, jahiaComponent } from "@jahia/javascript-modules-library";
import { MyComponentClient } from "./MyComponent.client";
import "./component.css";

type Props = { title?: string; itemsJson?: string };

jahiaComponent(
  { nodeType: "namespace:myComponent", displayName: "My Component", componentType: "view" },
  ({ title, itemsJson }: Props, { renderContext }) => {
    // Serialize any non-primitive data to JSON strings
    const mode = renderContext.getMode();          // "edit" | "preview" | "live"
    const isEditMode = renderContext.isEditMode(); // boolean

    return (
      <Island
        component={MyComponentClient}
        props={{ title, itemsJson, mode, isEditMode }}
      />
    );
  }
);
```

**Rules:**
- ❌ NEVER `<Island component={Client} props={props} />` — `props` is a JCR proxy, not a plain object
- ✅ ALWAYS destructure every prop by name and reconstruct as a plain literal
- All Island props must be JSON-serializable: strings, numbers, booleans, null, plain objects/arrays
- `JCRNodeWrapper`, `renderContext`, Java objects — never pass these to Island

---

### Passing Edit Mode Context to the Client

The client component has no access to `renderContext`. The server must pass it explicitly.

**Server:**
```tsx
jahiaComponent(
  { nodeType: "namespace:contactForm", componentType: "view" },
  ({ submitLabel }: Props, { renderContext }) => {
    const mode = renderContext.getMode();       // "edit" | "preview" | "live"
    const siteKey = (renderContext.getSite() as JCRSiteNode).getSiteKey();
    const language = renderContext.getMainResource().getLocale().getLanguage();

    return (
      <Island
        component={ContactFormClient}
        props={{ submitLabel, mode, siteKey, language }}
      />
    );
  }
);
```

**Client — uses `mode` to guard interactive behavior:**
```tsx
type Props = {
  submitLabel?: string;
  mode: string;       // "edit" | "preview" | "live"
  siteKey: string;
  language: string;
};

export function ContactFormClient({ submitLabel, mode, siteKey, language }: Props) {
  const [status, setStatus] = useState<"idle" | "pending" | "success" | "error">("idle");
  const isFormEnabled = mode !== "edit";  // disable form submission in edit mode

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isFormEnabled) return;
    // ...
  }

  return (
    <form onSubmit={handleSubmit} suppressHydrationWarning={mode === "edit"}>
      <button type="submit" disabled={!isFormEnabled}>{submitLabel}</button>
    </form>
  );
}
```

**`suppressHydrationWarning`** — apply on interactive elements when the Jahia content editor may inject markup (drag handles, edit overlays) that causes React hydration mismatches:
```tsx
<div className="interactive-wrapper" suppressHydrationWarning={mode === "edit"}>
  {/* editor injects overlay elements here in edit mode */}
</div>
```

---

### `useTranslation()` in Client Components

`react-i18next` works identically in both `.server.tsx` and `.client.tsx`. The Vite plugin bundles `settings/locales/*.json` automatically.

**Client component:**
```tsx
import { useTranslation } from "react-i18next";

export function GalleryClient({ items, mode }: Props) {
  const { t } = useTranslation();
  return (
    <section>
      <h2>{t("gallery.title")}</h2>
      <p>{t("gallery.itemCount", { count: items.length })}</p>
    </section>
  );
}
```

**`settings/locales/en.json`:**
```json
{
  "gallery": {
    "title": "Photo Gallery",
    "itemCount": "{{count}} photos"
  }
}
```

No additional setup needed — the same i18n instance is shared between server and client.

---

### Client-Side Data Fetching (GraphQL)

When the client needs to fetch data after hydration (pagination, search, lazy-loaded content), call the Jahia GraphQL endpoint directly via `fetch`. **This is the only supported client-side data API — no REST endpoints, no external APIs.**

```tsx
import { useState, useCallback } from "react";

const NEWS_QUERY = `
  query GetNews($siteKey: String!, $language: String!, $offset: Int!, $limit: Int!) {
    jcr(workspace: LIVE) {
      nodesByQuery(
        query: "SELECT * FROM [ns:newsItem] WHERE ISDESCENDANTNODE('/sites/${siteKey}/contents/news') ORDER BY [jcr:created] DESC"
        limit: $limit
        offset: $offset
      ) {
        nodes {
          uuid
          name
          displayName
          properties(names: ["title", "summary"]) { name value }
        }
      }
    }
  }
`;

type Props = { siteKey: string; language: string; initialItems: string; mode: string };

export function NewsGridClient({ siteKey, language, initialItems, mode }: Props) {
  const [items, setItems] = useState(() => JSON.parse(initialItems));
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(items.length);

  const loadMore = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/modules/graphql", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept-Language": language },
        body: JSON.stringify({
          query: NEWS_QUERY,
          variables: { siteKey, language, offset, limit: 6 },
        }),
      });
      const { data } = await res.json();
      const newItems = data.jcr.nodesByQuery.nodes;
      setItems((prev: unknown[]) => [...prev, ...newItems]);
      setOffset((prev: number) => prev + newItems.length);
    } finally {
      setLoading(false);
    }
  }, [siteKey, language, offset]);

  return (
    <div>
      <div className="news-grid">
        {items.map((item: { uuid: string; displayName: string }) => (
          <div key={item.uuid}>{item.displayName}</div>
        ))}
      </div>
      <button onClick={loadMore} disabled={loading}>
        {loading ? "Loading…" : "Load more"}
      </button>
    </div>
  );
}
```

**Rules:**
- Always pass `siteKey` and `language` from the server (the client cannot read them otherwise)
- Use `workspace: LIVE` in client GraphQL queries (visitors only see published content)
- The server renders the initial batch; the client only fetches additional pages
- Pre-serialize the initial server data: `props={{ initialItems: JSON.stringify(serverItems) }}`

---

### Lazy Hydration — `delayMs`

Defer hydration for components that are not immediately visible (below the fold, tabs, modals). This improves Largest Contentful Paint on pages with many Islands.

```tsx
// Hydrate after 150 ms — below-the-fold gallery
<Island component={GalleryClient} props={...} delayMs={150} />

// Hydrate after 500 ms — far below the fold or low-priority
<Island component={TestimonialsClient} props={...} delayMs={500} />

// No delay — interactive components that must be ready immediately (forms, nav)
<Island component={ContactFormClient} props={...} />
```

**Guidelines:**
- `delayMs={0}` or omit — hero/header interactive elements, forms above the fold
- `delayMs={150}` — below-the-fold sections (most common for carousels, galleries)
- `delayMs={500}` — footer widgets, tertiary content

---

### URL State Management in Client Components

When a client component needs to reflect state in the URL (filters, pagination, search), use `URLSearchParams` and `history.pushState()` — never change `window.location` (causes a full reload).

```tsx
import { useState, useEffect } from "react";

export function ExpertiseGridClient({ initialCategory, mode }: Props) {
  const [category, setCategory] = useState(() => {
    if (typeof window === "undefined") return initialCategory ?? "all";
    return new URLSearchParams(window.location.search).get("cat") ?? initialCategory ?? "all";
  });

  function selectCategory(cat: string) {
    setCategory(cat);
    // Reflect selection in URL without page reload
    const params = new URLSearchParams(window.location.search);
    if (cat === "all") {
      params.delete("cat");
    } else {
      params.set("cat", cat);
    }
    history.pushState(null, "", `?${params.toString()}`);
  }

  // Sync back on browser back/forward
  useEffect(() => {
    const handler = () => {
      const params = new URLSearchParams(window.location.search);
      setCategory(params.get("cat") ?? "all");
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  return (
    <div>
      <div className="filter-bar">
        {["all", "banking", "markets", "advisory"].map((cat) => (
          <button
            key={cat}
            className={category === cat ? "active" : ""}
            onClick={() => selectCategory(cat)}
          >
            {cat}
          </button>
        ))}
      </div>
      {/* filtered items */}
    </div>
  );
}
```

---

### Passing Structured Config to Island

When the client needs multiple configuration values (API endpoint, workspace, paths), group them into a single config object rather than individual props. The server assembles it; the client just reads it.

**Server:**
```tsx
jahiaComponent(
  { nodeType: "namespace:searchWidget", componentType: "view" },
  (_, { renderContext }) => {
    const siteKey = (renderContext.getSite() as JCRSiteNode).getSiteKey();
    const language = renderContext.getMainResource().getLocale().getLanguage();
    const mode = renderContext.getMode();

    const config = {
      siteKey,
      language,
      mode,
      contentPath: `/sites/${siteKey}/contents`,
      apiUrl: "/modules/graphql",
    };

    return <Island component={SearchWidgetClient} props={{ config }} />;
  }
);
```

**Client:**
```tsx
type Config = {
  siteKey: string;
  language: string;
  mode: string;
  contentPath: string;
  apiUrl: string;
};

export function SearchWidgetClient({ config }: { config: Config }) {
  const { siteKey, language, mode, apiUrl } = config;
  // ...
}
```

---

### Form State Machine Pattern

Interactive forms follow a four-state machine: `idle → pending → success | error`.

```tsx
type FormStatus = "idle" | "pending" | "success" | "error";

export function ContactFormClient({ submitUrl, feedbackMsg, mode }: Props) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<FormStatus>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const isEditMode = mode === "edit";

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (isEditMode || status === "pending") return;

    setStatus("pending");
    try {
      const form = e.currentTarget;
      const body = new FormData(form);
      const res = await fetch(submitUrl, { method: "POST", body });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus("success");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  }

  if (status === "success") {
    return <div className="form-success">{feedbackMsg ?? t("form.success")}</div>;
  }

  return (
    <form onSubmit={handleSubmit} suppressHydrationWarning={isEditMode}>
      <input name="email" type="email" required disabled={isEditMode} />
      <button type="submit" disabled={isEditMode || status === "pending"}>
        {status === "pending" ? t("form.submitting") : t("form.submit")}
      </button>
      {status === "error" && <p className="form-error">{errorMsg}</p>}
    </form>
  );
}
```

---

Before reporting that files are created, verify:

1. **Attribute preservation**: Count attributes (data-*, aria-*, role, id) in the HTML Fragment from your spec. Your TSX must have the same count.
2. **Class name fidelity**: Every CSS class in the HTML Fragment appears exactly as-is in your className strings — no renaming, no CSS Module refs.
3. **Dynamic content**: All hardcoded lists (navigation, footer links, locale selectors) come from props or JCR queries, never string literals.
4. **Noscript fallbacks**: If the HTML Fragment has `<noscript>`, your TSX includes it (use dangerouslySetInnerHTML for raw HTML inside noscript).
5. **Resource bundle entries**: Confirm that `settings/resources/{module-name}.properties` was updated with **both** `.label` AND `.ui.tooltip` for the type itself and every property. Count: one `.label` + one `.ui.tooltip` per property. Missing tooltips = fail.
6. **No URL string fields**: Scan the CND. If ANY field has type `string` and its name contains `url`, `link`, `href`, `path` → replace with the `seumix:linkTo` mixin pattern + `resolveCtaHref()`. Zero URL string fields are allowed.
7. **CTA pattern**: If the spec had `ctaLabel`/`ctaLink` as inline string fields, verify they were converted to `+ * (namespace:ctaButton)` child slots instead.
8. **jmix:mainResource card links**: If this is a card/list view for a `needsFullPage: true` type, confirm it uses `buildNodeUrl(currentNode)` for the detail URL — no link field on the node.
9. **fullPage view**: If `needsFullPage: true` in the spec, confirm `fullPage.server.tsx` was created and `jmix:mainResource` is in the CND supertypes.
10. **Cache properties**: If the component uses `useJCRQuery` or `useGQLQuery`, confirm `properties: { "cache.expiration": "..." }` is set on `jahiaComponent()` and `server.render.addCacheDependency()` is called with the queried content path.
11. **Edit-mode empty state**: If the component renders a dynamic list (from JCR query), confirm there is an empty-state message guarded by `renderContext.isEditMode()`.
12. **Placeholder image**: If an image prop is optional (weakreference without mandatory), confirm the placeholder fallback pattern is used.
13. **Island props safety**: If the component has a `.client.tsx`, confirm:
    - Props are destructured individually (never `props={props}`)
    - `mode` from `renderContext.getMode()` is passed to the client
    - `suppressHydrationWarning={mode === "edit"}` is applied on interactive DOM wrappers
    - Form submit buttons are `disabled={mode === "edit"}`
    - `useTranslation()` is used in the client for any user-facing strings (not hardcoded English)

Report any discrepancies.

## After Writing Files

Report:
- Files created (paths)
- Any decisions made (e.g. "server-only — no interactive features detected")
- Any warnings or assumptions
