---
name: support-create-view
description: Implement a React view (.server.tsx + CSS Module) for a Jahia component. Use as a building block inside 07-implement-components.
type: production
phase: support
status: active
allowed-tools: Bash, Read, Write, Edit
---

## Overview

A **view** tells Jahia how to render a content type. Views are React components (TypeScript/TSX) registered with the `jahiaComponent` function. They follow the **Single Directory Component (SDC)** pattern alongside the `definition.cnd`.

---

## File naming convention

| Filename | Meaning |
|---|---|
| `default.server.tsx` | Default server-side rendered view |
| `<name>.server.tsx` | Named view (e.g. `small.server.tsx`) |
| `<name>.client.tsx` | Client-side rendered (interactive) view |

A node type can have **multiple views**. When `name` is omitted in `jahiaComponent`, the view is the default.

---

## Step 1 — Create the view file

In the component folder (`src/components/<Category>/<Name>/`), create `default.server.tsx`:

```tsx
import { jahiaComponent, buildNodeUrl, RenderChildren, RenderChild } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";
import classes from "./component.module.css";

jahiaComponent(
  {
    componentType: "view",       // always "view" for a component (use "template" for page templates)
    nodeType: "namespace:typeName",
    displayName: "Human Readable Name",
    // name: "small",            // omit for default view; set for named views
  },
  ({ title, subtitle, background }: Props) => (
    <section className={classes.root}>
      <h2>{title}</h2>
      <p>{subtitle}</p>
    </section>
  ),
);
```

`jahiaComponent` **returns its second argument** (the React component). Export it to reuse the component directly in other views:

```tsx
// small.server.tsx — registered as a named view AND exported for direct reuse
export const SmallHero = jahiaComponent(
  { componentType: "view", nodeType: "ns:heroSection", name: "small" },
  ({ title, background }: Props) => <header style={{ backgroundImage: `url(${buildNodeUrl(background)})` }}><h1>{title}</h1></header>,
);

// fullPage.server.tsx — reuse the component directly without going through Jahia rendering
import { SmallHero } from "../Hero/Section/small.server.jsx";
<SmallHero title={title} background={cover} />
```

### When implementing a view from existing HTML

When you have a source HTML fragment to translate (e.g. from `/jahia-dev-import-from`), apply only **mechanical transformations**:

- `class=` → `className=`
- Void elements: `<img>`, `<input>`, `<br>` → self-close with ` />`
- `{placeholder}` text → `{propName}` matching `Props`

**Never** remove, rearrange, or simplify elements. Every `data-*`, `aria-*`, `role`, `id`, `<noscript>`, and `<source>` must appear in the TSX output. Carousel and slider wrapper `id`s in particular must be preserved verbatim — JS libraries use them for initialization.

**Self-check before finishing:** Count the attributes on 2-3 key elements in the source HTML. If the source `<div>` has 6 attributes and your TSX has 4, you dropped something — go back.

**CSS class names:** Rename source HTML class names to CSS Module keys (`hero__title` → `classes.heroTitle`). If the component also imports a vendor CSS file as a static asset (see `jahia-dev-import-from`), those vendor classes stay as plain strings in the JSX — they are not processed by CSS Modules.

---

## Step 2 — Import Props from types.ts

Always import `Props` from `./types.js` (not `./types.ts` — use `.js` extension at import time):

```ts
import type { Props } from "./types.js";
```

If `types.ts` doesn't exist yet, create it first (see `jahia-dev-define-content-type` skill).

---

## CMS rule — never hardcode links or URLs

> ⚠️ **This is a CMS. All links must come from contributed content — never from hardcoded strings in code.**

> **NEVER use an external link (`j:linkType: "external"`) to point to an internal Jahia page.** Use `"internal"` with `j:linknode` instead. An external URL hardcoded to an internal path breaks on environment changes, language switches, workspace toggling (live/preview), and vanity URL rewrites.

```tsx
// ❌ Wrong — hardcoded URL
<a href="https://www.jahia.com">Jahia</a>
<a href="/en/documentation">Documentation</a>

// ❌ Wrong — external link used for an internal page
// j:linkType: "external", j:url: "/sites/mySite/documentation.html"

// ✅ Correct — internal link to a JCR node
switch (props["j:linkType"]) {
  case "internal": return <a href={buildNodeUrl(props["j:linknode"])}>{props.label}</a>;
  case "external": return <a href={props["j:url"]}>{props.label}</a>;  // only for truly external URLs
}

// ✅ Correct — URL resolved from a JCR node at render time
<a href={buildNodeUrl(currentNode)}>{title}</a>
```

This applies everywhere: `href`, `src`, `action`, `data-url`. If a link needs to appear on screen, it must have a corresponding contributed field (`j:linkType`, `weakreference`, or similar). The only exception is links within the CMS UI itself (edit mode chrome).

---

## Step 3 — Use library helpers as needed

### `buildNodeUrl(node)` — convert a JCR node to a URL

```tsx
import { buildNodeUrl } from "@jahia/javascript-modules-library";

<img src={buildNodeUrl(coverNode)} alt="Descriptive alt text" />
<header style={{ backgroundImage: `url(${buildNodeUrl(background)})` }}>
```

**Options** (second argument):

| Option | Default | Use |
|---|---|---|
| `extension` | `.html` | Change output extension, e.g. `extension: ".pdf"` |
| `language` | current language | Override language: `language: "fr"` |
| `mode` | current mode | Force workspace: `"edit"`, `"preview"`, or `"live"` |
| `parameters` | — | Append query params: `parameters: { page: "2" }` |

> ⚠️ **Always guard optional nodes**: `buildNodeUrl(undefined)` throws `"Expected a node in buildNodeUrl, received undefined"`. If the prop is optional in the CND, guard it:
> ```tsx
> // ❌ Crashes when background is not set
> style={{ backgroundImage: `url(${buildNodeUrl(background)})` }}
>
> // ✅ Safe
> style={background ? { backgroundImage: `url(${buildNodeUrl(background)})` } : undefined}
> ```

> ⚠️ **Caching rule**: Never render properties of a **weakreference** node directly in the same view. Doing so will produce stale output because Jahia's cache is based on the referencing node, not the referenced one. Instead, render the referenced node using `<RenderChild>` (or a dedicated sub-view), or call `addCacheDependency` explicitly.

### `RenderChildren` — render child nodes with optional pagination and filtering

```tsx
import { RenderChildren } from "@jahia/javascript-modules-library";

// All children
<RenderChildren />

// Offset-based pagination
<RenderChildren pagination={{ count: 10, start: 0 }} />

// Page-based pagination (for paginator UI)
<RenderChildren pagination={{ count: 10, page: 0 }} />

// Filter by node type — string (single type) or function
<RenderChildren filter="ns:cardItem" />
<RenderChildren filter={(node) => node.isNodeType("ns:highlight")} />

// Combined
<RenderChildren pagination={{ count: 6, page: 0 }} filter="ns:blogPost" />
```

### `RenderChild` — render a specific named child node

```tsx
import { RenderChild } from "@jahia/javascript-modules-library";

<RenderChild name="hero" />                    // default view
<RenderChild name="hero" view="small" />       // named view
```

### `Render` — render any arbitrary JCR node or virtual node

```tsx
import { Render } from "@jahia/javascript-modules-library";

// Render a specific node by reference (also solves the weakreference cache issue)
<Render node={cityNode} view="name" />

// Render a virtual node — no JCR storage, no editor interaction needed
// Use for components that take no parameters and need no per-page configuration
<Render content={{ nodeType: "namespace:navBar" }} />
```

### `linkTypeInitializer` — rendering links

When a CND type uses `choicelist[linkTypeInitializer]`, the `j:linkType` property is a discriminator, NOT a URL. Use a `switch` statement:

```tsx
import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "namespace:callToAction" },
  (props: Props) => {
    switch (props["j:linkType"]) {
      case "internal":
        return <a href={buildNodeUrl(props["j:linknode"])}>{props.label}</a>;
      case "external":
        return <a href={props["j:url"]} title={props["j:linkTitle"]}>{props.label}</a>;
      default:
        return <span>{props.label}</span>;
    }
  },
);
```

### `getChildNodes` — iterate over child nodes in code (READ-ONLY derivation ONLY)

> 🚨 **EDITABILITY RULE (non-negotiable).** `getChildNodes(...).map(...)` to raw markup renders on the
> public site but the children are **NOT editable in jContent / Page Builder** — editors cannot select,
> add, reorder, or edit them. Use `getChildNodes` **only** for read-only *structural derivation* where the
> "children" are not editable content of this node — e.g. building a nav menu from the site's `jnt:page`
> tree. For any **editable child content the component owns** (carousel slides, top-bar social links,
> partner logos, gallery items, CTA buttons, FAQ items, list cards, …) you MUST render with
> **`<RenderChildren />`** (or `<RenderChild name="x" />`, or an `<Area>`), and the parent type must be a
> `jmix:list, jmix:renderableList orderable` container with a `+ * (ns:childType)` child definition. That is
> the ONLY way the children get Page Builder edit wrappers. This is exactly what made a migration
> "inexploitable" — socials/slides built with getChildNodes+`<a>` couldn't be edited. Compare the working
> sial-paris `sialp:topBar` (`jmix:list, jmix:renderableList orderable` + `+ * (sialp:socialLink)`, rendered
> with `<RenderChildren />`) vs a broken `getChildNodes(...).map(...<a>...)` topbar.
>
> **Validate in the editor, not just the public render:** after building, open the page in jContent Page
> Builder and confirm every component (header, top-bar, footer, hero/carousel, each section) is selectable
> and its children add/reorder. A page that renders publicly but is unselectable in jContent has FAILED.

```tsx
import { getChildNodes, buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

jahiaComponent(
  { componentType: "view", nodeType: "namespace:navBar" },
  (_, { renderContext, mainNode }) => {
    // Get all child pages of the site root
    const pages = getChildNodes(renderContext.getSite(), -1, 0,
      (node: JCRNodeWrapper) => node.isNodeType("jnt:page")
    );
    return (
      <nav>
        <ul>
          {pages.map(page => (
            <li key={page.getPath()}>
              <a
                href={buildNodeUrl(page)}
                aria-current={page.getPath() === mainNode.getPath() ? "page" : undefined}
              >
                {page.getProperty("jcr:title").getString()}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    );
  },
);
```

`getChildNodes(node, limit, offset, filterFn)` — `limit: -1` means no limit.

### `useServerContext` — access rendering context

```tsx
jahiaComponent(
  { componentType: "view", nodeType: "ns:type" },
  ({ title }: Props, { renderContext, currentNode, mainNode, jcrSession, bundleKey }) => {
    const isEdit = renderContext.isEditMode();
    const siteKey = renderContext.getSite().getName();
    return <div data-edit={isEdit}>{title}</div>;
  },
);
```

| Context field | Type | What it is |
|---|---|---|
| `renderContext` | `RenderContext` | Full rendering context (site, workspace, edit mode, user) |
| `currentNode` | `JCRNodeWrapper` | The component's own JCR node |
| `mainNode` | `JCRNodeWrapper` | The page's main resource node |
| `currentResource` | `Resource` | The render resource |
| `jcrSession` | `JCRSessionWrapper` | Current JCR session — do NOT hold across requests |
| `bundleKey` | `string` | Module bundle key (e.g. `"my-module"`) |

### Cache properties — controlling fragment caching

```tsx
jahiaComponent(
  {
    componentType: "view",
    nodeType: "namespace:price",
    properties: {
      "cache.expiration": "60",   // re-render at most once per minute
    },
  },
  ({ price }: Props) => <span>{price}</span>,
);
```

> Cache only applies in **live mode**. Edit and preview modes bypass the cache entirely.

### `buildModuleFileUrl` — URL to a static module asset

```tsx
import { buildModuleFileUrl, AddResources } from "@jahia/javascript-modules-library";

// Inject a vendor CSS file into the page head
<AddResources type="css" url={buildModuleFileUrl("css/vendor.min.css")} />

// Reference a bundled image
<img src={buildModuleFileUrl("images/placeholder.svg")} alt="" />
```

Never hardcode `/modules/<name>/javascript/apps/...` paths — use `buildModuleFileUrl` so the path resolves correctly across environments.

---

## Step 4 — Add CSS with CSS Modules

Create a `component.module.css` file in the same folder:

```css
.root {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 2rem;
}
```

Import and use in the view:

```tsx
import classes from "./component.module.css";

<section className={classes.root}>
```

> ⚠️ **CSS Modules hash class names at build time.** An inline `<script>` tag cannot reference a CSS Module class by name. For any element that a script needs to target, use a `data-*` attribute as the hook.

### ⚠️ CSS grid: `auto-fit` vs `auto-fill`

```css
/* ❌ auto-fill — leaves gaps when items don't fill the row */
grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));

/* ✅ auto-fit — items stretch to fill the full row */
grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
```

---

## Step 5 — Creating a named (non-default) view

```tsx
jahiaComponent(
  {
    componentType: "view",
    nodeType: "namespace:typeName",
    displayName: "Small View",
    name: "small",      // ← this registers a named view
  },
  ({ title }: Props) => <span className={classes.small}>{title}</span>,
);
```

---

## Step 5b — Creating a client-side interactive component (Island Architecture)

### When to use client vs server rendering

| Use `.server.tsx` for… | Use `.client.tsx` for… |
|---|---|
| Static HTML, CMS content, navigation | Buttons, toggles, counters, forms |
| Reading JCR/GQL data | `useState`, `useEffect`, browser events |
| SEO-important content | Animations, browser-only libraries |

### Client component

```tsx
// src/components/Counter/Counter.client.tsx
import { useState } from "react";
import classes from "./component.module.css";

interface Props {
  label: string;         // only serializable types allowed as Island props
  initialCount?: number;
}

export default function Counter({ label, initialCount = 0 }: Props) {
  const [count, setCount] = useState(initialCount);
  return (
    <div className={classes.counter}>
      <button type="button" onClick={() => setCount(c => c - 1)}>-</button>
      <span>{label}: {count}</span>
      <button type="button" onClick={() => setCount(c => c + 1)}>+</button>
    </div>
  );
}
```

> ⚠️ **Only the default export** of a `.client.tsx` file can be used as an island component.
> ⚠️ **Props must be serializable**: only strings, numbers, booleans, plain objects, and arrays. You cannot pass `JCRNodeWrapper`, `renderContext`, or Java objects.

### Wrap with `<Island>` in the server view

```tsx
// src/components/Counter/default.server.tsx
import { jahiaComponent, Island } from "@jahia/javascript-modules-library";
import Counter from "./Counter.client.jsx";     // .jsx at import time
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "namespace:counter" },
  ({ label, initialCount }: Props) => (
    <div>
      <Island component={Counter} props={{ label, initialCount }} />
    </div>
  ),
);
```

---

## Step 5c — Add front-end UI labels (locales)

Any string that appears in the rendered HTML and is not a JCR property value must come from `settings/locales/`.

```tsx
import { useTranslation } from "react-i18next";

const { t } = useTranslation();

<button>{t("hero.cta.label")}</button>
<img alt={t("alt.hero", { title })} />
```

Add to both `en.json` and `fr.json`:

```json
{
    "hero": {
        "cta": {
            "label": "Discover more"
        }
    }
}
```

---

## Step 5d — Language switcher

```tsx
import { getSiteLocales, buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";

jahiaComponent(
  { componentType: "view", nodeType: "ns:languageSwitcher" },
  (_, { renderContext, currentNode }) => {
    const locales = getSiteLocales(renderContext.getSite());
    const invalidLanguages: string[] = currentNode.getPropertyAsString("j:invalidLanguages")?.split(" ") ?? [];

    return (
      <ul>
        {locales
          .filter(locale => !invalidLanguages.includes(locale))
          .filter(locale => currentNode.hasI18N(renderContext.getSite().getLocale(locale)))
          .map(locale => (
            <li key={locale}>
              <a href={buildNodeUrl(currentNode, { language: locale })}>{locale.toUpperCase()}</a>
            </li>
          ))}
      </ul>
    );
  },
);
```

---

## Step 6 — Push to Jahia

```bash
# Always use this — never use yarn dev from an agent (it's interactive-only)
yarn build && yarn jahia-deploy
```

---

## Validation checklist
- [ ] `jahiaComponent` registered with correct `nodeType` (matches CND)
- [ ] `Props` imported from `./types.js`
- [ ] `buildNodeUrl` used for any image or node URL
- [ ] Weakreference-backed content rendered via sub-view (`RenderChild`), not inline property access
- [ ] Interactive UI (carousels, tabs) flattened in edit mode with editor hints
- [ ] No JS carousel markup (Swiffy Slider, Swiper, etc.) in a server-only view — use flex layout
- [ ] No `container` + `col-*` on the same element — use inline `maxWidth: "1140px"` on the content wrapper
- [ ] Structural/shared nodes rendered with `readOnly` prop
- [ ] Semantic HTML used (`<article>`, `<section>`, `<nav>`, `<header>`, `<footer>`)
- [ ] Images have meaningful `alt` text (not empty `alt=""` unless decorative)
- [ ] No hardcoded UI strings — all button labels, headings, messages use `t("key")` from `settings/locales/`
- [ ] `settings/locales/en.json` and `fr.json` both updated with any new keys
- [ ] CSS Module created and imported
- [ ] **If client-side**: component is in `.client.tsx`, wrapped with `<Island>` in the server view
- [ ] **If client-side**: all props passed to Island are serializable (no JCR objects)
- [ ] `yarn build && yarn jahia-deploy` run after all changes
- [ ] Component renders without errors in Page Builder

## Troubleshooting
> https://academy.jahia.com/tutorials-get-started/front-end-developer/making-a-hero-section

### `container` + `col-*` on the same element — component is full-width

**Symptom:** Section renders at full viewport width (e.g. 2560px) instead of capped at 1140px.

**Cause:** Bootstrap `col-12` (and any `col-*`) sets `max-width: 100%` which silently overrides `container`'s `max-width: 1140px` when both classes are on the same element. No error, no warning.

**Fix:** Never put both on the same element. For the inner content wrapper, use inline style instead of the `container` class:
```tsx
// Wrong: col-12 wins, full width
<section className="component my-section col-12">
  <div className="component-content container">  {/* max-width: 100% — broken */}

// Right: inline style always wins
<section className="component my-section col-12">
  <div className="component-content" style={{ maxWidth: "1140px", margin: "0 auto", width: "100%" }}>
```

### JS carousel shows only the first item in SSR

**Cause:** Libraries like Swiffy Slider, Swiper, and Glide set `overflow: hidden` on their container and translate slides via JS. In `.server.tsx` views with no client island, JS never runs — only slide 0 is visible.

**Fix:** Render carousels as a plain flex layout in server views. Add a client island only if animated sliding is required:
```tsx
// Instead of Swiffy Slider or any JS carousel markup:
<ul style={{ display: "flex", flexWrap: "wrap", gap: "20px", listStyle: "none", padding: 0 }}>
  {items.map((item) => <li key={item.getPath()}>...</li>)}
</ul>
```

### JSX vs HTML attribute differences

| Feature | HTML | JSX |
|---|---|---|
| CSS class | `class="..."` | `className="..."` |
| Inline style | `style="color:red"` | `style={{ color: 'red' }}` |
| Event handler | `onclick="fn()"` | `onClick={fn}` |
| Comments | `<!-- -->` | `{/* */}` |
| Boolean attributes | `disabled` | `disabled={true}` or just `disabled` |

## References

- JavaScript modules monorepo: https://github.com/Jahia/javascript-modules
- Preparing for i18n: https://academy.jahia.com/documentation/jahia-cms/jahia-8-2/developer/javascript-module-development/preparing-for-internationalization-i18n
