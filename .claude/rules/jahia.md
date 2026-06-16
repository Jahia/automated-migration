---
name: jahia-js-module
description: Core Jahia JS module development rules. Apply on all JS/React template set work.
---

# Jahia JavaScript Module Rules

1. **Always invoke a skill before any Jahia task** — skills contain canonical patterns and API signatures. Never operate from memory alone.
2. **Never use `yarn dev` from an agent** — always deploy with `yarn build && yarn jahia-deploy`.
3. **Never hardcode URLs** — all navigable links must come from contributed content (`j:linkType`, `buildNodeUrl`).
4. **Always verify before creating** — check that content types are deployed and site keys are correct before GraphQL mutations.
5. **All props are optional at runtime** — even mandatory CND fields. Always guard against `undefined`.
6. **Always include `-H "Origin: http://localhost:8080"` in every GraphQL curl** — omitting it returns `Permission denied`.
7. **Accessibility is mandatory** — every component must pass WCAG 2.1 AA. Run `/jahia-dev-accessibility` after building.
8. **Never declare `jcr:title` in CND** — use `mix:title` as a supertype.
9. **`weakreference` without `picker` type = full JCR node browser** — add `picker[type='page']` only to restrict to pages.
10. **Never use `jmix:droppableContent` directly** — always define a custom module mixin that extends it.
11. **All modules ship EN and FR at minimum** — see `.agents/context/jahia-i18n-patterns.md`.
