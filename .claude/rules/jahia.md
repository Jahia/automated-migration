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

## Operational truths (learned running the full loop on 4 sites, P3)

20. **"Operation successful" is NOT "bundle started".** An unresolvable nodetype requirement leaves the OSGi bundle INSTALLED but never ACTIVE, silently — every page then 500s ("Couldn't find the template"). The deploy gate must poll `jcr.nodeTypesByNames(["<ns>:rawHtml"])` until the type actually appears (module start is async — allow ~180s, longer on redeploy under load). Root cause seen live: a CND `+ * (<ns>:fooItem)` referencing an UNDEFINED child type → `missing requirement nodetypes=<ns>:fooItem`. NEVER reference a `{node}Item` type that isn't emitted; a container with no typed child accepts `+ * (<nsmix>:component)`.

21. **The provisioning `createSite` action has NO languages parameter.** `SiteCreationInfo` carries `locale` (default) only — passing `languages:` in the YAML is silently ignored (`j:languages` ends up default-only). Set languages AFTER creation via GraphQL `mutateProperty(name:"j:languages").setValues([...])` (a clean JSON list — bash-escaping the mutation string silently no-ops). Settle ~3s first (the site node must exist in EDIT).

22. **A site bound to the WRONG templateSet cannot be JCR-patched — deleteSite + recreate.** A site created while its module was still starting can bind to another module's templateSet → HTTP 500 on every page. Setting `j:templatesSet` via GraphQL does NOT repair the runtime association (rule 19). The only fix is provisioning `deleteSite` then `createSite`. `create_site.sh` self-heals this.

23. **Clean published content with GraphQL EDIT `deleteNode`, not mark-for-deletion.** For skeleton/i18n nodes the `mark_for_deletion` + publish flow is UNRELIABLE (jmix:markedForDeletion survivors whose async deletion-publication never lands → "already exists" collisions on reload). `jcr(workspace:EDIT){deleteNode}` is synchronous and publication-state-agnostic; publish the PARENT once afterwards to purge LIVE.

24. **Publish a parent AFTER its subtree is complete, never during.** Publishing a container while its item children are still being created ABORTS the publication job — the EDIT nodes never reach LIVE (seen live: 2 big articles, translation-parity gaps). Create all children first, then publish the parent, then sweep the area.

25. **The MCP write path drops connections under sustained load.** A site with hundreds of media uploads gets `Connection reset by peer` cascading into lost content. `mcp_client` retries transient network faults (ConnectionReset/timeout/URLError) at the transport level — HTTP status responses are NOT retried (they carry tool errors). `content.create` also retries `already exists`/`failed unexpectedly` with backoff.

26. **The ground-truth LIVE side must run under the SAME offline resolution as the reference.** The reference renders fully offline; if the live side reaches the internet, external-only widgets (a OneTrust cookie banner from `cdn.cookielaw.org`) render on ONE side only and eat ~20 fidelity points. Route the live page's non-Jahia-host requests through the same `offlineRoute` as the reference.

27. **jContent is an SPA that never reaches `networkidle`.** Playwright edit-mode probes must navigate with `waitUntil:"domcontentloaded"` then POLL for the `editframe` iframe — a fixed wait or `networkidle` times out (60s) under load and reads as "Page Builder did not load". Also: a `License terms violation` in jContent after long uptime is usually transient — `docker compose restart jahia` clears it.

28. **`forms.editForm` is the source of truth for what an editor can actually edit.** To verify a node's contribution surface, query `forms.editForm` and assert each wired prop is a read-write field in an ACTIVATED fieldSet — this is exactly what Content Editor renders. Pixel fidelity + JCR state never prove editability; this does (gate G6a). G6b (Playwright) then confirms each item has a `[path]` edit frame in Page Builder.
