# Context — Jahia Link Patterns

**URL string fields are forbidden.** Never write `- ctaUrl (string)`, `- href (string)`, or any string property that holds a URL. These break when pages are renamed and bypass Jahia's link management system.

**For any navigable link (CTA, card link, nav item, button), declare `j:linkType` directly on the content type:**

```cnd
- j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
```

There is **no `linkTo` mixin**. Do not create one and do not extend one — add the `j:linkType` property to each type that needs a link.

> Do **not** declare `j:url` or `j:linknode` — they are provided automatically by Jahia's built-in mixins when `linkTypeInitializer` fires.

---

## How It Works

The `linkTypeInitializer` selector drives a UI in the content editor. When the editor picks a link type, Jahia **automatically adds the corresponding mixin** to the node:

| `j:linkType` value | Mixin added | Property provided | Type |
|---|---|---|---|
| `internal` | `jmix:internalLink` | `j:linknode` | `weakreference` → page/resource |
| `external` | `jmix:externalLink` | `j:url` | `string`, **i18n** (locale-dependent) |
| `none` | _(none)_ | _(none)_ | — |

> `j:url` is **i18n**. The JCR session is already locale-aware — `getProperty("j:url").getString()` returns the correct translated URL automatically.

---

## Pattern A — Component with a Single Link

Declare `j:linkType` directly on the component:

```cnd
// src/components/CtaBanner/definition.cnd
[namespace:ctaBanner] > jnt:content, namespace:componentMixin
 - j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
 - title (string) i18n
 - linkText (string) i18n
```

---

## Pattern B — Reusable CTA Button Child Nodes

Use when a component has multiple styled buttons or when the button style varies:

```cnd
// Reusable button type — declares j:linkType directly
[namespace:ctaButton] > jnt:content, namespace:componentMixin
 - j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
 - ctaLabel (string) i18n
 - variant (string, choicelist[resourceBundle]) = 'primary' autocreated < 'primary', 'secondary', 'ghost'

// Parent component — children are ctaButton nodes
[namespace:heroSection] > jnt:content, namespace:componentMixin
 - title (string) i18n
 + * (namespace:ctaButton)
```

---

## Server-Side Link Resolution (TSX)

The value lives in the `j:linkType` property. `j:linknode` and `j:url` come from the dynamically-injected mixins and are not statically typed in `Props`, so read them off `currentNode` rather than `props`.

### `resolveLinkHref` — canonical implementation

```tsx
import { buildNodeUrl } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

function resolveLinkHref(node: JCRNodeWrapper): string {
  if (!node.hasProperty("j:linkType")) return "#";
  const type = node.getProperty("j:linkType").getString();
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
const linkHref = resolveLinkHref(currentNode);

return linkHref !== "#" ? (
  <a href={linkHref} className="cta-button">{ctaLabel || t("event.register")}</a>
) : null;
```

> Render the link only when `linkHref !== "#"` — never show a broken `#` link. Guard against `isCancelled` too when relevant.

---

## GraphQL — Creating Links via API

### Internal link (page reference):
```graphql
mutation {
  jcr(workspace: EDIT) {
    mutateNode(pathOrId: "/sites/SITE/home/AREA/my-cta") {
      addMixins(mixins: ["jmix:internalLink"])
      setPropertiesBatch(properties: [
        { name: "j:linkType", value: "internal" }
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
        { name: "j:linkType", value: "external" }
        { name: "j:url", value: "https://example.com", language: "en" }
      ]) { path }
    }
  }
}
```

> Always set `j:linkType` alongside the mixin so the content editor shows the correct UI state.

---

## Quick Check Before Adding a Link Property

```bash
grep -n "j:linkType\|linkTypeInitializer" settings/definitions.cnd src/components/**/definition.cnd
```

- Need a link on a type? Add `- j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no` to that type.
- Never store a URL in a plain `string` field.

---

## Non-Negotiables

| Rule | Why |
|---|---|
| Never `- url (string)` or `- href (string)` | Breaks on page rename; bypasses link management |
| Never declare `j:url` or `j:linknode` in your CND | They are injected at runtime by Jahia's built-in `jmix:externalLink` / `jmix:internalLink` |
| No `linkTo` mixin | Declare `j:linkType (string, choicelist[linkTypeInitializer])` directly on each type that needs a link |
| Always scan for `url`, `link`, `href`, `src`, `path` field names | Auto-flag any string property holding a URL and replace with a `j:linkType` property |
