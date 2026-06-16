# Context — Jahia Link Patterns

**URL string fields are forbidden.** Never write `- ctaUrl (string)`, `- href (string)`, or any string property that holds a URL. These break when pages are renamed and bypass Jahia's link management system.

**Always use the `linkTo` mixin** for any navigable link (CTA, card link, nav item, button).

---

## The `linkTo` Mixin

Declare once in `settings/definitions.cnd` for the entire project — never re-declare per component:

```cnd
[namespace:linkTo] mixin
 - ctaType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
```

> Do **not** declare `j:url` or `j:linknode` — they are provided automatically by Jahia's built-in mixins when `linkTypeInitializer` fires.

### How It Works

The `linkTypeInitializer` selector drives a UI in the content editor. When the editor selects a link type, Jahia **automatically adds the corresponding mixin**:

| `ctaType` value | Mixin added | Property provided | Type |
|---|---|---|---|
| `internal` | `jmix:internalLink` | `j:linknode` | `weakreference` → page/resource |
| `external` | `jmix:externalLink` | `j:url` | `string`, **i18n** (locale-dependent) |
| `none` | _(none)_ | _(none)_ | — |

> `j:url` is **i18n**. The JCR session is already locale-aware — `getProperty("j:url").getString()` returns the correct translated URL automatically.

---

## Pattern A — Component with a Single Link

Extend the mixin directly on the component:

```cnd
// settings/definitions.cnd
[namespace:linkTo] mixin
 - ctaType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no

// src/components/CtaBanner/definition.cnd
[namespace:ctaBanner] > jnt:content, namespace:componentMixin, namespace:linkTo
 - title (string) i18n
 - linkText (string) i18n
```

---

## Pattern B — Reusable CTA Button Child Nodes

Use when a component has multiple styled buttons or when the button style varies:

```cnd
// Reusable button type — extends linkTo
[namespace:ctaButton] > jnt:content, namespace:componentMixin, namespace:linkTo
 - ctaLabel (string) i18n
 - variant (string, choicelist[resourceBundle]) = 'primary' autocreated < 'primary', 'secondary', 'ghost'

// Parent component — children are ctaButton nodes
[namespace:heroSection] > jnt:content, namespace:componentMixin
 - title (string) i18n
 + * (namespace:ctaButton)
```

---

## Server-Side Link Resolution (TSX)

### Which property name to use

Two conventions exist in Jahia projects:

| Convention | CND property | When used | Resolution strategy |
|---|---|---|---|
| Native Jahia | `j:linkType` | When extending `jmix:link` directly | `switch (props["j:linkType"])` — value is in props |
| Custom `linkTo` mixin | `ctaType` (or your name) | Project modules — recommended | `resolveCtaHref(currentNode)` — read node directly |

With the custom `linkTo` mixin, `j:linknode` and `j:url` come from dynamically-injected mixins and are not statically typed in `Props`. Reading them via `currentNode` is safer and does not require a discriminated union.

### `resolveCtaHref` — canonical implementation

```tsx
import { buildNodeUrl } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

function resolveCtaHref(node: JCRNodeWrapper): string {
  if (!node.hasProperty("ctaType")) return "#";
  const type = node.getProperty("ctaType").getString();
  if (type === "internal" && node.hasProperty("j:linknode")) {
    return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
  }
  if (type === "external" && node.hasProperty("j:url")) {
    // j:url is i18n — JCR session resolves locale automatically
    return node.getProperty("j:url").getString() ?? "#";
  }
  return "#";
}
```

**Usage in a view:**

```tsx
const ctaHref = resolveCtaHref(currentNode);

return ctaHref !== "#" ? (
  <a href={ctaHref} className="cta-button">{ctaLabel || t("event.register")}</a>
) : null;
```

> Render the CTA button only when `ctaHref !== "#"` — never show a broken `#` link. Guard against `isCancelled` too when relevant.

---

## GraphQL — Creating Links via API

### Internal link (page reference):
```graphql
mutation {
  jcr(workspace: EDIT) {
    mutateNode(pathOrId: "/sites/SITE/home/AREA/my-cta") {
      addMixins(mixins: ["jmix:internalLink"])
      setPropertiesBatch(properties: [
        { name: "ctaType", value: "internal" }
        { name: "j:linknode", value: "/sites/SITE/home/target-page", type: WEAKREFERENCE }
      ]) { path }
    }
  }
}
```

### External link (URL, i18n):
```graphql
mutation {
  jcr(workspace: EDIT) {
    mutateNode(pathOrId: "/sites/SITE/home/AREA/my-cta") {
      addMixins(mixins: ["jmix:externalLink"])
      setPropertiesBatch(properties: [
        { name: "ctaType", value: "external" }
        { name: "j:url", value: "https://example.com", language: "en" }
      ]) { path }
    }
  }
}
```

> Always set `ctaType` alongside the mixin so the content editor shows the correct UI state.

---

## Quick Check Before Adding a Link Property

Always read `settings/definitions.cnd` first:

```bash
grep -n "linkTo\|linkTypeInitializer" settings/definitions.cnd
```

- If `[namespace:linkTo]` already exists — **extend it, never re-declare it**
- If it does not exist — declare it once in `settings/definitions.cnd`, then extend

---

## Non-Negotiables

| Rule | Why |
|---|---|
| Never `- url (string)` or `- href (string)` | Breaks on page rename; bypasses link management |
| Never declare `j:url` or `j:linknode` in your CND | They conflict with Jahia's built-in `jmix:externalLink` / `jmix:internalLink` |
| Declare `[namespace:linkTo]` once in `settings/definitions.cnd` | Not per-component — extend instead |
| Always scan for `url`, `link`, `href`, `src`, `path` field names | Auto-flag any string property holding a URL and replace with `linkTo` mixin |
