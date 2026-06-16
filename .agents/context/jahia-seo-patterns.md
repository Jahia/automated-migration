# Context — Jahia SEO Patterns

SEO in Jahia JS modules is handled through a dedicated `nsmix:seo` mixin, a `SeoMetaTags` server component injected in the Layout `<head>`, and a set of editorial conventions that prevent the most common ranking pitfalls. All public-facing `jmix:mainResource` types must apply this mixin.

---

## `nsmix:seo` Mixin — CND Definition

Declare once in `settings/definitions.cnd`. Every content type that can be a main resource (a page) extends it.

```cnd
[nsmix:seo] mixin
 - metaTitle (string) i18n
 - metaDescription (string, textarea) i18n
 - canonicalUrl (string) indexed=no
 - ogImage (weakreference, picker[type='image']) < jmix:image
 - ogType (string, choicelist[resourceBundle]) = 'website' autocreated < 'website', 'article', 'event', 'product'
```

Apply to every `jmix:mainResource` page type:

```cnd
[ns:myPage] > jnt:content, mix:title, nsmix:seo, jmix:mainResource
```

### `.properties` Labels

```properties
# settings/resources/module_en.properties
nsmix:seo.metaTitle.label=SEO Title (max 60 chars)
nsmix:seo.metaTitle.title=Overrides the page title in search engine results. Leave blank to use the page title.
nsmix:seo.metaDescription.label=Meta Description (max 160 chars)
nsmix:seo.metaDescription.title=Summary shown in search engine results. Google truncates beyond 160 characters.
nsmix:seo.canonicalUrl.label=Canonical URL
nsmix:seo.canonicalUrl.title=Override the canonical URL. Leave blank to use the live page URL.
nsmix:seo.ogImage.label=Social Share Image
nsmix:seo.ogType.label=Open Graph Type
nsmix:seo.ogType.website.label=Website
nsmix:seo.ogType.article.label=Article
nsmix:seo.ogType.event.label=Event
nsmix:seo.ogType.product.label=Product
```

### TypeScript Interface

```ts
// src/commons/types.ts
export interface SeoProps {
  metaTitle?: string;
  metaDescription?: string;
  canonicalUrl?: string;
  ogImage?: JCRNodeWrapper;
  ogType?: "website" | "article" | "event" | "product";
}
```

---

## `SeoMetaTags` Server Component — Full Implementation

Place in `src/commons/SeoMetaTags.tsx` and call it from `Layout.tsx` inside `<head>`.

```tsx
import {
  buildNodeUrl,
  getNodeProps,
  getSiteLocales,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

export function SeoMetaTags() {
  const { renderContext, mainNode, currentResource } = useServerContext();

  const props = getNodeProps(mainNode) as {
    metaTitle?: string;
    metaDescription?: string;
    canonicalUrl?: string;
    ogImage?: JCRNodeWrapper;
    ogType?: string;
    "jcr:title"?: string;
  };

  // Title: metaTitle → jcr:title → node name
  const title =
    props.metaTitle ||
    props["jcr:title"] ||
    mainNode.getName();

  const description = props.metaDescription || "";

  // Canonical: editor override → live URL via buildNodeUrl
  const canonical =
    props.canonicalUrl ||
    buildNodeUrl(mainNode);

  const ogType = props.ogType || "website";

  // og:image URL (only when set)
  const ogImageUrl = props.ogImage
    ? buildNodeUrl(props.ogImage)
    : undefined;

  // hreflang — one link per site locale + x-default
  const siteLocales = getSiteLocales();
  const localeEntries = Object.keys(siteLocales);
  const defaultLocale = renderContext.getSite().getDefaultLanguage?.() ?? localeEntries[0];

  return (
    <>
      <title>{title}</title>
      {description && <meta name="description" content={description} />}
      <link rel="canonical" href={canonical} />

      {/* Open Graph */}
      <meta property="og:title" content={title} />
      {description && <meta property="og:description" content={description} />}
      <meta property="og:url" content={canonical} />
      <meta property="og:type" content={ogType} />
      {ogImageUrl && <meta property="og:image" content={ogImageUrl} />}

      {/* Twitter Card */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={title} />
      {description && <meta name="twitter:description" content={description} />}
      {ogImageUrl && <meta name="twitter:image" content={ogImageUrl} />}

      {/* hreflang — multilingual alternate links */}
      {localeEntries.length > 1 &&
        localeEntries.map((lang) => (
          <link
            key={lang}
            rel="alternate"
            hrefLang={lang}
            href={buildNodeUrl(mainNode, { language: lang })}
          />
        ))}
      {localeEntries.length > 1 && defaultLocale && (
        <link
          rel="alternate"
          hrefLang="x-default"
          href={buildNodeUrl(mainNode, { language: defaultLocale })}
        />
      )}
    </>
  );
}
```

Use it in `Layout.tsx`:

```tsx
<head>
  <meta charSet="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <SeoMetaTags />
  <AddResources type="css" url={buildModuleFileUrl("assets/index.css")} />
  {head}
</head>
```

---

## Heading Hierarchy Convention

The page template owns the `<h1>`. Components must never use `<h1>`.

| Context | Element |
|---|---|
| Page title (`jcr:title`) in the page template | `<h1>` — always, exactly once |
| Top-level section heading inside a component | `<h2>` |
| Sub-section heading | `<h3>` |
| Card title inside a list component | `<h3>` (the list heading is `<h2>`) |

For components that may be placed at different nesting depths, expose a `headingLevel` prop:

```tsx
interface Props {
  title?: string;
  headingLevel?: "h2" | "h3" | "h4";
}

function SectionTitle({ title, headingLevel: Tag = "h2" }: Props) {
  return title ? <Tag>{title}</Tag> : null;
}
```

```
✅  Template renders: <h1>{pageTitle}</h1>
✅  Component renders: <h2>Section title</h2> / <h3>Card title</h3>
❌  Component renders: <h1>Hero title</h1>     ← second h1 on the page
❌  Component renders: <h4>Section title</h4>  ← skipped h2 and h3
```

---

## Image SEO and Core Web Vitals

### LCP Hero Images

The Largest Contentful Paint element (above-the-fold hero image) must **never** be lazy-loaded:

```tsx
{/* ✅ LCP hero — loads immediately, signals high priority */}
<img
  src={imgProps.src}
  alt={imgProps.alt}
  width={imgProps.width}
  height={imgProps.height}
  loading="eager"
  fetchPriority="high"
/>

{/* ❌ Never lazy-load the hero */}
<img src={...} loading="lazy" />
```

### All Other Images

Always supply explicit `width` and `height` to prevent Cumulative Layout Shift (CLS):

```tsx
{/* ✅ Explicit dimensions prevent CLS */}
<img
  src={imgProps.src}
  alt={imgProps.alt}
  width={imgProps.width}
  height={imgProps.height}
  loading="lazy"
/>

{/* ❌ Missing dimensions → layout shift as image loads */}
<img src={imgProps.src} alt={imgProps.alt} loading="lazy" />
```

### `imageNodeToImgProps` — Read Dimensions from JCR

```tsx
// src/commons/libs/imageNodeToImgProps/index.ts
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { buildNodeUrl } from "@jahia/javascript-modules-library";

interface ImgProps {
  src: string;
  alt: string;
  width?: number;
  height?: number;
  srcSet?: string;
}

export function imageNodeToImgProps(
  node: JCRNodeWrapper,
  widths: number[],
): ImgProps {
  // Read a dedicated imageAlt field — never use jcr:title (often a filename)
  const alt = node.hasProperty("imageAlt")
    ? node.getPropertyAsString("imageAlt")
    : "";

  const src = buildNodeUrl(node);
  const isVector = node.getName().endsWith(".svg");
  if (isVector) return { src, alt };

  const intrinsicWidth = node.hasProperty("j:width")
    ? parseInt(node.getPropertyAsString("j:width"), 10)
    : undefined;
  const intrinsicHeight = node.hasProperty("j:height")
    ? parseInt(node.getPropertyAsString("j:height"), 10)
    : undefined;

  const clampedWidths = intrinsicWidth
    ? widths.filter((w) => w <= intrinsicWidth).concat([intrinsicWidth])
    : widths;

  const srcSet = [...new Set(clampedWidths)]
    .map((w) => `${src}?w=${w} ${w}w`)
    .join(", ");

  return { src, alt, width: intrinsicWidth, height: intrinsicHeight, srcSet };
}
```

> `jcr:title` is often set to the original upload filename (e.g., `hero-photo-v3-FINAL.jpg`). **Never use it as the default `alt` text.** Require a dedicated `imageAlt` field on the content type.

### Decorative Images

```tsx
{/* ✅ Decorative image — empty alt + aria-hidden */}
<img src={divider.src} alt="" aria-hidden="true" /> {/* decorative */}
```

---

## Canonical URLs and hreflang — Jahia Multilingual Sites

### How Jahia Renders URLs

Jahia renders each page at a URL shaped like `/sites/{siteKey}/home/page-name.html`. The live and preview workspaces use different base paths. `buildNodeUrl` handles workspace and locale automatically — always use it.

```tsx
// ✅ Correct — buildNodeUrl picks up the current workspace and locale
const url = buildNodeUrl(node);

// ✅ Correct — explicit locale override (e.g., for hreflang links)
const frUrl = buildNodeUrl(node, { language: "fr" });

// ❌ Never hardcode URL segments
const url = `/sites/mysite/home/${node.getName()}.html`;
```

### Vanity URLs

Jahia's vanity URL module creates 301 redirects from the canonical path to editor-defined vanity URLs (e.g., `/about` → `/sites/mysite/home/about-us.html`). Once a vanity URL is active, it becomes the stable canonical:

1. Editor sets vanity URL in jContent > Page > Vanity URLs tab.
2. The canonical `<link>` should reflect the vanity URL after it is live.
3. `buildNodeUrl` does **not** return the vanity URL — editors must enter it manually in the `canonicalUrl` field exposed by `nsmix:seo`.

### hreflang — Multilingual Sites

Always emit one `<link rel="alternate">` per locale plus `x-default`. Omitting these causes Google to treat locale variants as duplicate content.

```
✅  /sites/mysite/home/about.html?lang=en  → hreflang="en"
✅  /sites/mysite/home/about.html?lang=fr  → hreflang="fr"
✅  x-default → points to the site's default locale
❌  Only <link rel="canonical"> without hreflang on a multilingual site
```

---

## JSON-LD Structured Data

### `renderJsonLd` Helper

```tsx
// src/commons/renderJsonLd.tsx
export function renderJsonLd(data: Record<string, unknown>) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
```

### Article Schema

```tsx
import { renderJsonLd } from "~/commons/renderJsonLd";

// In a jmix:mainResource view for ns:article:
renderJsonLd({
  "@context": "https://schema.org",
  "@type": "Article",
  headline: title,
  description: metaDescription,
  image: ogImageUrl,
  datePublished: mainNode.getPropertyAsString("jcr:created"),
  dateModified: mainNode.getPropertyAsString("jcr:lastModified"),
  author: { "@type": "Organization", name: renderContext.getSite().getDisplayableName() },
  url: buildNodeUrl(mainNode),
});
```

### Event Schema

```tsx
renderJsonLd({
  "@context": "https://schema.org",
  "@type": "Event",
  name: title,
  startDate: startDate,  // ISO 8601 string from jevt:startDate property
  endDate: endDate,
  location: {
    "@type": "Place",
    name: locationName,
  },
  offers: price
    ? { "@type": "Offer", price, priceCurrency: "EUR" }
    : undefined,
  url: buildNodeUrl(mainNode),
});
```

### BreadcrumbList Schema

Traverse `currentNode` ancestors to build breadcrumb items:

```tsx
function buildBreadcrumbs(node: JCRNodeWrapper): object[] {
  const crumbs: object[] = [];
  let current: JCRNodeWrapper | null = node;
  while (current && current.isNodeType("jnt:page")) {
    crumbs.unshift({
      "@type": "ListItem",
      position: 0, // filled below
      name: current.hasProperty("jcr:title")
        ? current.getPropertyAsString("jcr:title")
        : current.getName(),
      item: buildNodeUrl(current),
    });
    current = current.getParent() as JCRNodeWrapper | null;
  }
  return crumbs.map((c, i) => ({ ...c, position: i + 1 }));
}

// Usage:
renderJsonLd({
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  itemListElement: buildBreadcrumbs(mainNode),
});
```

### WebSite Schema with SearchAction (Homepage Only)

```tsx
// Emit only when mainNode is the site home page
if (mainNode.getPath() === `/sites/${siteKey}/home`) {
  renderJsonLd({
    "@context": "https://schema.org",
    "@type": "WebSite",
    url: buildNodeUrl(mainNode),
    potentialAction: {
      "@type": "SearchAction",
      target: { "@type": "EntryPoint", urlTemplate: `${siteBaseUrl}/search?q={search_term_string}` },
      "query-input": "required name=search_term_string",
    },
  });
}
```

---

## Sitemap and robots.txt in Jahia

### Sitemap Module

Jahia's `sitemap-module` auto-generates `/sitemap.xml`. Install via module provisioning:

```xml
<!-- provisioning/site-init.yaml or import.xml -->
<module id="sitemap" version="..." />
```

Pages excluded automatically:
- Nodes with `jmix:nolive` — draft/archive folders and hidden pages
- Nodes without live publish rights

Never manually list pages in a sitemap — rely on the module.

### Excluding Folders from Sitemap

Draft and archive content containers must have `jmix:nolive`. Cross-reference: this is the same convention documented for import.xml structure.

```cnd
// ❌ A page visible in sitemap but intended as an archive container
[ns:archiveFolder] > jnt:content

// ✅ Explicitly excluded from live rendering and sitemap
[ns:archiveFolder] > jnt:content, jmix:nolive, jmix:systemNameReadonly
```

### robots.txt

Place at `src/files/robots.txt` in the template-set (served as a site file). Do not hardcode `/cms/` prefixed Jahia internal paths in `Disallow` — they change between deployments:

```txt
User-agent: *
Disallow: /administration/
Sitemap: https://example.com/sitemap.xml
```

---

## URL Structure and Vanity URLs

### Node Naming Conventions

Node names become URL path segments. Apply these rules when creating or importing content:

| Rule | Example |
|---|---|
| Lowercase only | `about-us` not `About-Us` |
| Hyphens as separators, no underscores | `our-services` not `our_services` |
| No accents or special characters | `equipe` not `équipe` |
| Maximum 50 characters | — |
| Never change after go-live | Add a vanity URL redirect instead |

```
✅  /sites/mysite/home/our-services
✅  /sites/mysite/home/contact-us
❌  /sites/mysite/home/OurServices
❌  /sites/mysite/home/our_services
❌  /sites/mysite/home/équipe-commerciale
```

### Vanity URL Workflow

1. Editor opens jContent > page node > Vanity URLs tab.
2. Adds vanity URL (e.g., `/about`) — Jahia creates a 301 redirect.
3. Developer updates `canonicalUrl` in the `nsmix:seo` mixin to the vanity URL.
4. Never remove a vanity URL that was indexed by search engines.

---

## Non-Negotiables

| Rule | Why |
|---|---|
| Never use `jcr:title` as default `alt` text | It is often a filename — `hero-v3-FINAL.jpg` is not a useful description |
| Always emit `<link rel="canonical">` | Prevents duplicate content on preview/live/vanity URL variants |
| Always emit `hreflang` on multilingual sites | Google treats locale variants as duplicates without it |
| LCP hero image must use `loading="eager" fetchPriority="high"` | Core Web Vitals ranking signal — lazy loading the hero delays LCP |
| All `<img>` must have explicit `width` and `height` | Missing dimensions cause Cumulative Layout Shift (CLS) |
| `metaDescription` max 160 chars | Google truncates beyond this in search result snippets |
| Use `buildNodeUrl` for all internal URLs | Handles workspace (live/preview) and locale automatically |
| Vanity URL → must also update `canonicalUrl` field | `buildNodeUrl` does not return the vanity URL |
