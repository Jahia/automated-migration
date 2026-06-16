---
name: migration-rules
description: Non-negotiable rules for Jahia website migration projects. Always apply when migrating a site.
---

# Jahia Migration Rules

## Core principles

1. **Never manually create component files** — always use `/5-components` which spawns parallel subagents per component. Manual creation misses resource bundles, icons, and the deduplication step.

2. **HTML fragments must match exactly** — the TSX output must produce the same HTML structure as the source. Never simplify, reorder, or omit wrapper elements, `data-*` attributes, or ARIA attributes.

3. **Use `richtext` for body/description fields** — editors need to format migrated content. Never use plain `string` for fields that contain HTML in the source.

4. **Always verify component registration** before creating content. Run `docker logs <jahia-container> | grep "Registered Jahia component"` and confirm the component name appears.

5. **Properties are always optional in `types.ts`** — even mandatory CND fields. Guards like `prop?.value ?? ''` are required everywhere in views.

6. **CND property order is strict:** `(type, selector) = 'default' keywords < constraints`

## Navigation

7. **Navigation goes 3 levels deep** via a JCR-driven component. Never hardcode nav links. Use `getChildNodes` filtered by `jmix:navMenuItem`. See `.agents/context/jahia-navigation-patterns.md` for the full 3-level render pattern.

## Links

8. **Every contributor-facing link uses `linkTypeInitializer`** — `j:linkType (string, choicelist[linkTypeInitializer])` in the CND. Never store a URL in a plain `string` field.

9. **`j:url` and `j:linknode` must be declared explicitly** in the module's `linkTo` mixin — `linkTypeInitializer` is UI-only (shows/hides fields in editor). If omitted, mutations throw `ConstraintViolationException`.

## Tags and Categories

10. **Never create custom tag or category CND fields.** Use Jahia built-ins:
    - Free-form tags: extend `jmix:tagged` (injects `j:tagList`)
    - Taxonomy: `(weakreference, category[autoSelectParent=false]) multiple`

## Structural components

11. **Never use `jmix:list`** on container components. Use explicit child node definitions: `+ * (namespace:childType)`.

12. **Every module ships `JCRQuery` and `GridRow`** adapted to the module namespace. These are created by `/5-components` or manually before editor handoff.

## Resource bundles

13. **Every field key requires a `ui.tooltip` companion key.** No exceptions.

```properties
ns_hero.title=Title
ns_hero.title.ui.tooltip=Main heading at the top of the section.
ns_hero.j:linkType=Call to Action
ns_hero.j:linkType.ui.tooltip=Link for the CTA button. Choose internal page or external URL.
```

## Content creation

14. **Two-phase publishing for i18n** — always create translation nodes (`j:translation_en`, etc.) explicitly. Publishing the node alone does not publish translations.

15. **Images are WEAKREFERENCE** — upload to DAM first, then reference by UUID. Never store image URLs as strings in content.

16. **Absolute areas (header, footer) are created once** at `/sites/{siteKey}/home/header` and `footer`. Never drop them as regular page components.

## Mixins

17. **Extract shared fields into mixins before writing the second content type.** Common: `nsmix:cta` (link + label), `nsmix:media` (image + alt), `nsmix:badge` (label + color), `nsmix:seo` (metaTitle + metaDesc).
