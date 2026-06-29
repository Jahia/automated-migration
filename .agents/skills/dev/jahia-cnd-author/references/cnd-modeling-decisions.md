# CND Content Modeling Decisions

## Scale of thumbs

A well-scoped module has: **1–4 page templates, 5–10 content types, 2–5 mixins, 1–4 views per type.**
If a request exceeds this, flag it and split work into sessions.

---

## Semantic vs generic types

| Use semantic types for… | Use generic types for… |
|---|---|
| Business entities: articles, team members, events | Visual composition: banners, feature rows |
| Items that appear in listings/collections | One-off sections, layout containers |
| Content with business logic or user restrictions | Reusable UI blocks without meaning |
| Content that needs a detail page (`jmix:mainResource`) | |

When in doubt, prefer semantic — its evolutions are easier to design.

---

## Weakreference vs children

| Use children when… | Use weakreference when… |
|---|---|
| Parent is a visual container (CTAs inside a hero) | Internal links (call to action targets, page links) |
| Children have no life outside the parent | Many-to-many relationships (author ↔ blog post) |
| Always created together | Content managed/reused elsewhere |
| Each child has multiple properties (label + link) | Each item is just a reference to an existing node |

- Many-to-many = MUST use `weakreference multiple`
- One-to-many = prefer children when parent is the container

---

## Mixin vs child node vs inheritance

| Use mixin when… | Use child nodes when… | Use inheritance when… |
|---|---|---|
| Reusing properties across unrelated types | Multiple instances needed (multiple CTAs) | Retaining original views + adding fields in new views |
| At most one instance per component | | |

**Avoid inheritance in general** — it duplicates types in the editor picker.

Never extend anything other than `jnt:content` (or your base mixin). To add fields to a type you don't control, use a mixin with `extends`:

```cnd
[nsmix:morePageFields] mixin extends=jnt:page
 - myField (string) i18n
```

---

## Pages vs jmix:mainResource

| Use pages when… | Use jmix:mainResource when… |
|---|---|
| Content is a standalone page with no structured data | Content needs both a listing card AND a detail page |
| No programmatic listing/filtering needed | Content collections (blog posts, events, team members) |

---

## Common reusable mixin patterns

| Mixin name | Properties | When to use |
|---|---|---|
| `nsmix:cta` | `label (string) i18n`, `j:linkType (string, choicelist[linkTypeInitializer])` | Any type with a button/link |
| `nsmix:media` | `image (weakreference, picker[type='image']) < jmix:image` | Any type with an image |
| `nsmix:seo` | `metaTitle (string) i18n`, `metaDescription (string, textarea) i18n` | Any `jmix:mainResource` type |
| `nsmix:badge` | `badgeText (string) i18n`, `badgeColor (string, color)` | Cards, teasers |

Always extract to a mixin when the same set of properties appears on 2+ types.

---

## Spec template (interactive mode)

```
Component: [PascalCase name]
Description: [what editors create with this]
Fields:
  - name: data type, i18n?, mandatory?, multiple?
Views: [default / card / fullPage / small]
Used where: [page area / content folder / child of <Parent>]
Repeatable children: [no / yes: describe]
```

## Layout / rendering variation: property vs view vs new type

When sections look different but hold the **same data** (text + image left vs
right, 1/2/3 columns, a colour/`variant`, a size), absorb the variation at the
lowest level. **Always optimise for the contributor's UX.**

| Lever | Use when the variation is… | Who controls it | Cost |
|---|---|---|---|
| **Layout property** (`(string, choicelist) < 'left','right'`) | a **per-instance toggle** an editor flips (image side, columns, colour, size, `displayMode`) | the **contributor**, in Content Editor, on the node | one field; view branches |
| **Named view** (`x.server.tsx`) | **structurally different markup** for the same data (`card` vs `fullPage`, hero vs teaser) | the **integrator / template** at placement | one file; no CND change |
| **New type** | the **data shape** genuinely differs (different fields) | operator-approved `halt` | a whole type |

**Prefer the property.** A text+image-left/right block is **one type with an
`imagePosition (string, choicelist) = 'left' < 'left','right'` property**, not two
views and never two types — the editor sets it inline, sees the choice in the
form, and never has to know about "views". Reach for a view only when the markup
truly diverges; reach for a new type only when the fields differ.

```cnd
- imagePosition (string, choicelist) = 'left' autocreated < 'left', 'right'
- columns (string, choicelist) = '3' autocreated < '1', '2', '3'
- variant (string, choicelist) = 'default' autocreated < 'default', 'highlight'
```
The view reads it: `className={`block image-${imagePosition ?? 'left'}`}`. Give
every such field an i18n label + `ui.tooltip` so the choice is self-explanatory.
