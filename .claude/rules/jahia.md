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
6. **Always include `-H "Origin: $JAHIA_URL"` in every GraphQL curl** — the Origin must match `$JAHIA_URL` (port-sensitive: a mismatched port is a hard, empty-body 403; omitting it returns `Permission denied`). Example: `curl -u "$JAHIA_USER:$JAHIA_PASS" -H "Origin: $JAHIA_URL" -H 'Content-Type: application/json' -X POST "$JAHIA_URL/modules/graphql" -d '{"query":"..."}'`.
7. **Accessibility is mandatory** — every component must pass WCAG 2.1 AA. Run `/jahia-dev-accessibility` after building.
8. **Never declare `jcr:title` in CND** — use `mix:title` as a supertype.
9. **`weakreference` without `picker` type = full JCR node browser** — add `picker[type='page']` only to restrict to pages.
10. **Never use `jmix:droppableContent` directly** — always define a custom module mixin that extends it.
11. **All modules ship EN and FR at minimum** — see `.agents/context/jahia-i18n-patterns.md`.
12. **`jmix:cache` does not exist in Jahia 8.2** — never use it in CND supertypes. List containers use `jmix:list, jmix:renderableList` only.
15. **`AbsoluteArea` belongs in `Layout.tsx` only, never in template files.** Use `useServerContext()` inside Layout to get `renderContext`. The `parent` prop must be `site.getNode("home")` — NOT `renderContext.getSite()` (which stores content at the site root, not `/home/header`).
16. **MainResource template must use `nodeType: "jmix:mainResource"` with `priority: -1`**, not `nodeType: "jnt:page"` with a name. Using `jnt:page` creates a selectable page template instead of a fallback for content nodes.
17. **Import Layout with `.js` extension** in template files: `import { Layout } from "../Layout.js"`. Using `.jsx` is wrong.
18. **Never pass `renderContext` as a second argument to page templates** just to call `getSite()`. Use `useServerContext()` inside the Layout component instead.
19. **Never create sites via GraphQL `addNode`** — always use the provisioning API `createSite` action. A manually created `jnt:virtualsite` node is missing essential initialization: home page, ACLs, files folder, groups folder, template set binding, and installed modules. After creation, verify `j:languages`, `j:installedModules`, and that `home`/`files`/`contents`/`groups` children all exist.
13. **Namespace conflicts persist across deploys** — even after uninstalling a module, its namespace prefix/URI stays in Jackrabbit's registry. Always check for conflicts with the Groovy console before deploying a new namespace. Use `/validate-module` as the mandatory gate before `/6-content`.
14. **`yarn jahia-deploy` returns `{}` on both success and failure** — always verify via GraphQL type query after deploy, not just by checking the deploy output.
