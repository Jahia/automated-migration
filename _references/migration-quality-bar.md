# Migration Quality Bar

Every skill in jahiaMigration produces output that must meet this bar before the user is told the task is done.

---

## HTML fidelity

- Zero layout regressions vs the reference site at 1440px and 375px.
- All CSS classes from the original HTML are present in the Jahia TSX (either as CSS Module keys or as imported vendor class strings).
- All `data-*`, `aria-*`, `id`, `role`, `<source>`, `<noscript>` attributes preserved verbatim.
- Interactive components (carousels, sliders, tabs, accordions) use Island architecture in render mode and flat fallback in edit mode.

## CND completeness

- Every user-facing string/text/richtext field has `i18n`.
- Every contributor-facing link uses `j:linkType (string, choicelist[linkTypeInitializer])`.
- No custom `tags` or `category` properties — use `jmix:tagged` and `category[autoSelectParent=false]`.
- Every resource bundle field key has a companion `.ui.tooltip` key.
- `mix:title` as supertype — never explicit `jcr:title` property.
- All props in `types.ts` use `?:` (optional).

## Navigation

- 3 levels rendered: L1 (top bar), L2 (dropdown), L3 (fly-out or sub-dropdown).
- All 4 nav item types supported: `jnt:page`, `jnt:navMenuText`, `jnt:nodeLink`, `jnt:externalLink`.
- `getNavItems` filter excludes `jmix:navMenu` containers.
- Language switcher uses `getSiteLocales()` — never hardcoded locale codes.

## Accessibility (WCAG 2.1 AA)

- Dropdown triggers have `aria-haspopup="true"` and `aria-expanded` reflecting open state.
- Active nav item uses `aria-current="page"`.
- Escape closes dropdowns and returns focus to trigger.
- Color contrast ≥ 4.5:1 for normal text, ≥ 3:1 for large text.
- All images have `alt` (empty string for decorative).

## Build and deploy

- `yarn build` exits 0 with no TypeScript errors.
- `yarn jahia-deploy` uploads successfully.
- Docker logs show `Registered Jahia component` for every new view.
- Existing pages still render after deploy (no regressions).

## Content

- All pages published (not just saved to default workspace).
- Content created in the correct site and language.
- Category and tag assignments use Jahia built-in taxonomy nodes — not string values.

## i18n

- EN and FR keys present for every field in `.properties` and `locales/`.
- No raw key strings visible in the rendered page (means a translation is missing).
- `loadNamespaces('module-name')` called before any UI extension registers.
