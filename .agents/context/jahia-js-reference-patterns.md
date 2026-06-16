# Context — Jahia JS Module Reference Patterns

Non-obvious patterns extracted from `luxe-jahia-demo`, the official Jahia JS template set reference module. Load this alongside `javascript-modules-library-api.md` when building production-quality template sets.

Source: `/Users/stephane/Runtimes/0.Modules/luxe-jahia-demo`

---

## Module layout (monorepo)

The reference module uses a Yarn 4 workspace with two packages:

```
<module>/
├── packages/
│   ├── template-set/          # The Jahia module — shipped to Jahia
│   │   ├── src/
│   │   │   ├── components/    # One folder per content type
│   │   │   ├── templates/     # Page templates (.server.tsx)
│   │   │   └── commons/       # Shared utilities (imageNodeToImgProps, etc.)
│   │   ├── settings/          # CND, .properties, import.xml, icons
│   │   └── package.json
│   └── design-system/         # Private package — CSS tokens, shared UI primitives
│       ├── src/
│       │   ├── variables.css  # CSS custom properties (colors, fonts, spacing)
│       │   ├── global.css     # Utility classes
│       │   └── index.ts       # Exports Grid, Form, UI, Icon components
│       └── package.json       # private: true
└── package.json               # workspace root
```

The design-system is imported by the template-set as a local package — not published. This separation keeps design tokens and reusable UI primitives out of the Jahia module layer.

---

## CSS custom properties — always with fallback defaults

**Every CSS variable use in a component MUST include a fallback value.** This ensures the component is usable even when no theme CSS is loaded, and makes the default legible in the source:

```css
/* ❌ Never — component breaks if theme is not loaded */
.card {
  background: var(--ns-color-surface);
  border-radius: var(--ns-radius-xl);
}

/* ✅ Always — component works standalone, theme overrides when present */
.card {
  background: var(--ns-color-surface, #ffffff);
  border-radius: var(--ns-radius-xl, 8px);
  box-shadow: var(--ns-shadow-card, 0 1px 3px rgba(0,0,0,0.06));
  transition: box-shadow var(--ns-transition-standard, 0.2s ease);
}
```

### Theme scoping via a wrapper class

Define all design tokens scoped to a single class (e.g. `.ns-themed`). This enables:
- Runtime theme switching by toggling the class on any ancestor element
- Multiple themes in the same page by nesting different scoped wrappers
- Zero conflict with the rest of the Jahia jcontent UI

```css
/* themes/default.css */
.ns-themed {
  --ns-color-brand: #0d6efd;
  --ns-color-brand-hover: #0a58ca;
  --ns-color-surface: #ffffff;
  --ns-color-surface-subtle: #f8f9fa;
  --ns-color-text-heading: #212529;
  --ns-color-text-body: #343a40;
  --ns-color-text-muted: #6c757d;
  --ns-radius-xl: 8px;
  --ns-shadow-card: 0 1px 2px rgba(0,0,0,0.075);
  --ns-shadow-card-hover: 0 4px 8px rgba(0,0,0,0.1);
  --ns-transition-standard: 0.15s ease-in-out;
}
```

```css
/* themes/crimson.css — overrides only the tokens that differ */
.ns-themed {
  --ns-color-brand: #e60028;
  --ns-color-brand-hover: #b5001e;
}
```

Apply in the page template Layout wrapper:

```tsx
<body className="ns-themed">
  {children}
</body>
```

Ship multiple theme CSS files (`default.css`, `crimson.css`, etc.) and let the site owner pick one via a page property or a module setting. Load with `<AddResources type="css" url={buildModuleFileUrl("themes/default.css")} />`.

### Variable naming convention

Use a module-specific prefix to avoid collisions with Jahia's UI or other modules:

```
--<module-prefix>-<category>-<variant>
--ailp-color-brand
--ailp-color-brand-hover
--ailp-radius-xl
--ailp-shadow-card
--ailp-transition-standard
```

Categories to define upfront: `color`, `radius`, `shadow`, `transition`, `font`, `spacing`.

---

## Design system — CSS custom properties

Define brand tokens in `design-system/src/variables.css`, not in component CSS Modules. This creates one source of truth for color, typography, and spacing:

```css
/* variables.css */
:root {
  /* Brand colors */
  --luxe-color-primary: #c29b40;
  --luxe-color-dark: #1b1a4e;

  /* Semantic aliases */
  --luxe-color-heading: var(--luxe-color-dark);
  --luxe-color-bg-secondary: #f6f6f6;
  --luxe-box-shadow: 4px 6px 17px 15px rgba(35, 33, 110, 0.1);

  /* Typography */
  --luxe-font-family-display: "Playfair Display Variable", serif;
  --luxe-font-family-body: "Inter Variable", sans-serif;
}
```

> ⚠️ The example color `--luxe-color-primary: #c29b40` (gold) has a contrast ratio of ~2.3:1 against white — this FAILS WCAG AA for text. Always verify brand colors with the [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/) before using them for text or interactive element borders.

#### Reduced-motion: always wrap transitions

```css
/* Default: no motion — transitions are 0ms */
:root {
  --ns-transition-standard: 0ms;
  --ns-transition-fast: 0ms;
}

/* Only animate when the user has not requested reduced motion */
@media (prefers-reduced-motion: no-preference) {
  :root {
    --ns-transition-standard: 0.2s ease;
    --ns-transition-fast: 0.1s ease;
  }
}
```

This pattern ensures transitions are off by default and only enabled for users who have not opted into reduced motion — the safest approach for accessibility.

Export shared grid breakpoints and spacing as `@value` so CSS Modules can import them:

```css
/* design-system/src/grid.css */
@value xs: 0;
@value sm: 576px;
@value md: 768px;
@value lg: 992px;
@value xl: 1200px;
@value xxl: 1400px;

/* design-system/src/spacing.css */
@value space_0: 0;
@value space_1: 0.5rem;
@value space_2: 1rem;
@value space_3: 2rem;
@value space_4: 3rem;
@value space_5: 5rem;
```

Consume in a component CSS Module:

```css
@value md from "design-system/src/grid.css";

@media (min-width: md) {
  .hero { padding: 4rem 0; }
}
```

---

## Page template — Layout wrapper pattern

All page templates share a **single `Layout.tsx`** that handles the HTML shell, `<head>` resources, SEO, and site-level areas. Individual templates only define their body structure.

```tsx
// src/commons/Layout.tsx
import { Area, AbsoluteArea, AddResources, buildModuleFileUrl, useServerContext } from "@jahia/javascript-modules-library";
import classes from "./layout.module.css";

interface LayoutProps {
  head?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Layout({ head, className, children }: LayoutProps) {
  const { renderContext } = useServerContext();
  return (
    <html lang={renderContext.getMainResourceLocale().getLanguage()}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <AddResources type="css" url={buildModuleFileUrl("assets/index.css")} />
        <SeoMetaTags />
        {head}
      </head>
      <body>
        <a href="#main-content" className={classes.skipLink}>Skip to content</a>
        <AbsoluteArea name="header" parent={renderContext.getSite()} readOnly="children" />
        <main id="main-content" className={className}>
          {children}
        </main>
        <AbsoluteArea name="footer" parent={renderContext.getSite()} readOnly="children" />
      </body>
    </html>
  );
}
```

Page templates then become minimal:

```tsx
// src/templates/Page/centered.server.tsx
jahiaComponent(
  { componentType: "template", nodeType: "jnt:page", name: "centered" },
  () => (
    <Layout>
      <Area name="header" nodeType="ns:header" numberOfItems={1} />
      <Area name="main" />
    </Layout>
  ),
);
```

---

## Cache invalidation — `addCacheDependency`

By default, a component's cache fragment is invalidated when its own node changes. Declare additional dependencies explicitly:

```tsx
import { server, useServerContext } from "@jahia/javascript-modules-library";

jahiaComponent(
  { componentType: "view", nodeType: "ns:gallery" },
  ({ images }: Props) => {
    const { renderContext } = useServerContext();

    // Invalidate when any referenced image node changes
    images?.forEach(imageNode => {
      server.render.addCacheDependency({ node: imageNode }, renderContext);
    });

    return <div>{/* render gallery */}</div>;
  },
);
```

For query-driven components, invalidate the entire subtree using a path regex:

```tsx
server.render.addCacheDependency(
  { flushOnPathMatchingRegexp: `/sites/${siteKey}/contents/blog/.*` },
  renderContext,
);
```

Cache tuning via `jahiaComponent` properties:

```tsx
jahiaComponent(
  {
    componentType: "view",
    nodeType: "ns:searchResults",
    properties: {
      "cache.expiration": "600",      // 10-minute TTL
      "cache.latch": "true",          // prevent thundering herd on cold cache
    },
  },
  () => { /* ... */ },
);
```

---

## Responsive images — `imageNodeToImgProps`

A reusable utility pattern for generating `<img>` props from a Jahia image node. Build this in `src/commons/libs/imageNodeToImgProps/`.

Key rules:
- Use a **dedicated `imageAlt` CND field** for alt text. NEVER pass `jcr:title` directly — it is often a filename or technical string.
- Pass `isLCP: true` for above-the-fold hero images to set `loading="eager"` and `fetchPriority="high"`.
- Always include `width` and `height` to prevent layout shift (CLS).

```tsx
/**
 * Build <img> props from a JCR image node (jmix:image).
 * @param node - the image JCRNodeWrapper
 * @param options.alt - explicit alt text from a dedicated CND field (e.g. imageAlt). NEVER pass jcr:title directly.
 * @param options.isLCP - true for above-the-fold hero images (sets loading="eager" fetchpriority="high")
 */
function imageNodeToImgProps(
  node: JCRNodeWrapper,
  options: { alt: string; isLCP?: boolean }
): React.ImgHTMLAttributes<HTMLImageElement> {
  const width = node.hasProperty("j:width") ? Number(node.getProperty("j:width").getString()) : undefined;
  const height = node.hasProperty("j:height") ? Number(node.getProperty("j:height").getString()) : undefined;
  return {
    src: buildNodeUrl(node),
    alt: options.alt,                          // empty string "" for decorative images
    width,
    height,
    loading: options.isLCP ? "eager" : "lazy",
    fetchPriority: options.isLCP ? "high" : undefined,
  };
}

// Usage — hero image (LCP candidate):
const imgProps = imageNodeToImgProps(featuredImage as JCRNodeWrapper, {
  alt: imageAlt ?? "",   // imageAlt is a dedicated CND field, not jcr:title
  isLCP: true,
});
<img {...imgProps} className={classes.hero} />

// Usage — card thumbnail:
const thumbProps = imageNodeToImgProps(thumbnail as JCRNodeWrapper, {
  alt: imageAlt ?? "", // alt="" marks it as decorative when no alt text provided
});
<img {...thumbProps} className={classes.thumb} />  {/* decorative */}
```

> `sizes` and `srcSet` are provided at the call site when needed — they depend on the layout context, not the image node.

---

## Dynamic grid columns with AbsoluteArea

For a multi-column layout where each column is an independent editorial area (editors can contribute independently to each column), use `AbsoluteArea` with names derived from the component node name:

```tsx
jahiaComponent(
  { componentType: "view", nodeType: "ns:columns" },
  ({ columnCount = 3 }: Props, { currentNode, renderContext }) => {
    const cols = Array.from({ length: columnCount }, (_, i) => i);
    return (
      <div className={classes.grid} style={{ gridTemplateColumns: `repeat(${columnCount}, 1fr)` }}>
        {cols.map(i => (
          <AbsoluteArea
            key={i}
            name={`${currentNode.getName()}-col-${i}`}
            parent={currentNode}
          />
        ))}
      </div>
    );
  },
);
```

This creates editable column areas whose names are stable per component instance (tied to the node name).

---

## CTA mixin pattern

For reusable call-to-action links across multiple content types, define a mixin instead of duplicating link fields:

**CND** (`settings/definitions.cnd`):
```cnd
[nsmix:cta] mixin
 - ctaLabel (string) i18n
 - ctaType (string, choicelist[linkTypeInitializer]) = 'none' autocreated mandatory
 // j:linknode and j:url are injected by Jahia's linkTypeInitializer — do NOT declare them
```

**TypeScript** — use a discriminated union with the optional mixin:

```ts
import type { JCRNodeWrapper } from "org.jahia.services.content";

type CTAProps =
  | { ctaType: "none"; ctaLabel?: string }
  | { ctaType: "internal"; ctaLabel?: string; "j:linknode"?: JCRNodeWrapper }
  | { ctaType: "external"; ctaLabel?: string; "j:url"?: string };

export interface Props {
  title?: string;
  subtitle?: string;
  cta?: CTAProps;   // optional — not all instances will have a CTA
}
```

**View** — render the CTA conditionally:

```tsx
function renderCTA(props: CTAProps) {
  switch (props.ctaType) {
    case "internal": return props["j:linknode"]
      ? <a href={buildNodeUrl(props["j:linknode"])}>{props.ctaLabel}</a>
      : null;
    case "external": return props["j:url"]
      ? <a href={props["j:url"]}>{props.ctaLabel}</a>
      : null;
    default: return null;
  }
}
```

---

## SEO meta tags pattern

Full `SeoMetaTags` component — emit in the page template `<head>`. Requires `nsmix:seo` mixin on the main resource node. Covers `<title>`, meta description, canonical, Open Graph, Twitter Card, and hreflang:

```tsx
import { buildNodeUrl, server, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

/**
 * SeoMetaTags — emit in the page template <head>.
 * Requires: nsmix:seo mixin on the main resource node.
 * Covers: <title>, meta description, canonical, Open Graph, Twitter Card, hreflang.
 */
function SeoMetaTags({
  mainNode,
  renderContext,
  currentResource,
}: {
  mainNode: JCRNodeWrapper;
  renderContext: any;
  currentResource: any;
}) {
  const locale = currentResource.getLocale().getLanguage();
  const siteKey = renderContext.getSite().getSiteKey();

  // Title — nsmix:seo metaTitle overrides jcr:title
  const metaTitle = mainNode.hasProperty("metaTitle")
    ? mainNode.getProperty("metaTitle").getString()
    : mainNode.hasProperty("jcr:title")
    ? mainNode.getProperty("jcr:title").getString()
    : mainNode.getName();

  const metaDescription = mainNode.hasProperty("metaDescription")
    ? mainNode.getProperty("metaDescription").getString()
    : null;

  // Canonical — nsmix:seo canonicalUrl overrides default
  const canonicalUrl = mainNode.hasProperty("canonicalUrl")
    ? mainNode.getProperty("canonicalUrl").getString()
    : buildNodeUrl(mainNode);

  // OG image
  const ogImageUrl = mainNode.hasProperty("ogImage")
    ? buildNodeUrl(mainNode.getProperty("ogImage").getNode() as JCRNodeWrapper)
    : null;

  const ogType = mainNode.hasProperty("ogType")
    ? mainNode.getProperty("ogType").getString()
    : "website";

  // hreflang — iterate all site locales
  const siteLocales: string[] = server.render.getSiteLocales?.(renderContext) ?? [locale];
  const hreflangLinks = siteLocales.map((loc) => ({
    loc,
    url: buildNodeUrl(mainNode, { language: loc }),
  }));
  const defaultLocale = siteLocales[0];

  return (
    <>
      <title>{metaTitle}</title>
      {metaDescription && <meta name="description" content={metaDescription} />}
      <link rel="canonical" href={canonicalUrl} />

      {/* Open Graph */}
      <meta property="og:title" content={metaTitle} />
      {metaDescription && <meta property="og:description" content={metaDescription} />}
      <meta property="og:url" content={canonicalUrl} />
      <meta property="og:type" content={ogType} />
      {ogImageUrl && <meta property="og:image" content={ogImageUrl} />}
      {ogImageUrl && <meta property="og:image:width" content="1200" />}
      {ogImageUrl && <meta property="og:image:height" content="630" />}

      {/* Twitter Card */}
      <meta name="twitter:card" content={ogImageUrl ? "summary_large_image" : "summary"} />
      <meta name="twitter:title" content={metaTitle} />
      {metaDescription && <meta name="twitter:description" content={metaDescription} />}
      {ogImageUrl && <meta name="twitter:image" content={ogImageUrl} />}

      {/* hreflang — multilingual */}
      {hreflangLinks.map(({ loc, url }) => (
        <link key={loc} rel="alternate" hrefLang={loc} href={url} />
      ))}
      <link rel="alternate" hrefLang="x-default" href={buildNodeUrl(mainNode, { language: defaultLocale })} />
    </>
  );
}
```

---

## Conditional CSS classes with `clsx`

Use `clsx` (or `classnames`) instead of string concatenation for conditional CSS Module classes:

```tsx
import clsx from "clsx";
import classes from "./component.module.css";

<section className={clsx(
  classes.root,
  isHighlighted && classes.highlighted,
  size === "large" && classes.large,
)} />
```

`clsx` is not bundled with `@jahia/javascript-modules-library` — add it to `package.json`:
```json
"dependencies": { "clsx": "^2.0.0" }
```

---

## Locale-aware number and date formatting

```tsx
const { currentResource } = useServerContext();
const locale = currentResource.getLocale().getLanguage(); // "en", "fr", "de"

// Number formatting (price, surface, etc.)
<span>{price?.toLocaleString(locale, { style: "currency", currency: "EUR" })}</span>

// Date formatting
<time dateTime={publicationDate}>
  {new Date(publicationDate).toLocaleDateString(locale, { dateStyle: "long" })}
</time>
```

---

## `gql.tada` — type-safe server-side GraphQL

For zero-runtime type safety in `useGQLQuery` calls, use `gql.tada` with the Jahia `schema.graphql` introspection file:

```bash
yarn add gql.tada
```

`tsconfig.json` plugin config:
```json
{
  "plugins": [{
    "name": "gql.tada/ts-plugin",
    "schema": "./schema.graphql"
  }]
}
```

Usage:

```tsx
import { graphql } from "gql.tada";
import { useGQLQuery } from "@jahia/javascript-modules-library";

const QUERY = graphql(`
  query GetEstate($path: String!) {
    jcr {
      nodeByPath(path: $path) {
        displayName
        property(name: "price") { value }
      }
    }
  }
`);

// data is fully typed — no `any`
const data = useGQLQuery(QUERY, { path });
```

The `schema.graphql` file is generated by Jahia's GraphQL introspection endpoint:
```bash
curl -H "Origin: http://localhost:8080" \
  http://localhost:8080/modules/graphql \
  -d '{"query":"{__schema{types{name}}}"}' \
  > schema.graphql
```

---

## `primary` keyword in CND

Mark the most important editorial field as `primary` — Jahia's editor UI uses this to show the field prominently:

```cnd
[ns:blogPost] > jnt:content, nsmix:component
 - title (string) i18n mandatory primary   // ← shown as the main field in the editor
 - subtitle (string, textarea) i18n
 - body (string, richtext) i18n mandatory
```

Only one property per type should be `primary`.

---

## `autocreated` with default values in CND

Use `autocreated` + a default to pre-populate a property when a new node is created. This avoids null-checks in views for fields that should always have a value:

```cnd
[ns:estate] > jnt:content, nsmix:component
 - country (string, choicelist[country]) = 'FR' autocreated mandatory
 - status (string, choicelist[resourceBundle]) = 'available' autocreated mandatory < 'available', 'sold', 'rented'
```

The `= 'FR'` is the default value. Combine with `mandatory` to ensure the field always has a value going forward, while `autocreated` ensures existing nodes without the property still get the default on first edit.

---

## Empty area workaround (known Jahia bug)

Empty `AbsoluteArea` and `Area` components do not render in preview mode when no content has been contributed yet. This causes the area to be invisible and editors cannot add content.

Workaround: render a virtual node as the area's parent to force the area chrome to appear:

```tsx
// Force the area to render even when empty
<Render
  content={{
    name: "navWrapper",
    nodeType: "jnt:contentList",
    children: [{ name: "nav", nodeType: "ns:navigationMenu" }],
  }}
/>
```

This is a platform bug tracked upstream. Check the Jahia GitHub before applying — it may be fixed in newer `javascript-modules-engine` versions.

---

## Build script conventions

**`package.json` scripts** (template-set):

```json
{
  "scripts": {
    "build": "tsc --noEmit && vite build",
    "dev": "vite build --watch",
    "jahia-deploy": "jahia-cli module:deploy"
  }
}
```

- `build` runs `tsc --noEmit` (type-check only, no emit) before Vite — catches type errors before bundling.
- `dev` uses `vite build --watch` (not `vite dev`) — Jahia requires the module to be built as a bundle, not served from Vite's dev server. **Never use `yarn dev` in an agent** — it's for local hot-reload only and does not deploy to Jahia.
- Type-check + build separation: Vite ignores TypeScript errors by design; the explicit `tsc --noEmit` is the safety gate.

**`tsconfig.json` key settings**:
```json
{
  "compilerOptions": {
    "jsx": "preserve",
    "noEmit": true,
    "strict": true,
    "baseUrl": ".",
    "paths": { "~/*": ["src/*"] },
    "plugins": [
      { "name": "typescript-plugin-css-modules" },
      { "name": "gql.tada/ts-plugin", "schema": "./schema.graphql" }
    ]
  }
}
```

- `jsx: "preserve"` lets Vite handle JSX transformation (React 19 automatic runtime).
- `paths: { "~/*": ["src/*"] }` — also set as `resolve.alias` in `vite.config.js` for runtime resolution.

---

## References

- Reference module: `/Users/stephane/Runtimes/0.Modules/luxe-jahia-demo`
- Jahia developer training: https://github.com/Jahia/developer-training/blob/main/js-training/slides.md
