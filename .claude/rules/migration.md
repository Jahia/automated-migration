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

9. **`j:linkType (string, choicelist[linkTypeInitializer])` is declared INLINE on the type; `j:url`/`j:linknode` are NEVER declared in a CND** — Jahia's `jmix:externalLink`/`jmix:internalLink` inject them at runtime. Verified against the 3 deployed reference modules (supercar/sial/lesalondelaphoto `settings/definitions.cnd`; `cnd_emit.py` encodes the pattern) AND by mutation on the deployed v2 module (acquia, 2026-07-03): setting `j:url` without the mixin is a `ConstraintViolation` (proof the property is not on the type), and **the mixin is applied by the Content-Editor choicelist flow, NOT by raw JCR writes** — an API loader must add `jmix:externalLink` explicitly (GraphQL `mutateNode.addMixins`; the MCP content tools accept no `mixins` argument today) before setting `j:url`.

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

14. **Process is EDIT-only; publication is a SINGLE FINAL act (Julian, 2026-07-04).** Never publish during loads or process probes — a stale LIVE is tolerated and expected. Per-node publication during loads corrupted the publication metadata: a naive `publish` no-ops in 1 ms (SUCCESSFUL job publishing NOTHING) while LIVE stays stale; the reliable reset is `unpublish` first (measured live on discoverasr — mcp_client `unpublish` docstring). Publish once at the end via `orchestration/assist/publish_site.sh <project> <site>` (files → chrome → per-page unpublish-first → publish → poll (name,uuid) alignment, ~300s trickle past `finished:true`), which ends with the strict `integrity.py --phase step_publish_final` belt. **i18n:** still create translation nodes (`j:translation_en`, etc.) explicitly in EDIT; they publish with the final act. **ALL verification runs against the EDIT workspace via authenticated preview — NO test ever touches LIVE (Julian, 2026-07-04).** Every gate, including ground truth / fidelity, fetches `/cms/render/default/{lang}/sites/{site}/{page}.html` with Basic auth (the EDIT render). An EDIT update is visible there immediately (~0.3s, no cache flush, no publication — measured), and the render is near byte-identical to LIVE (1 220 826 vs 1 220 731 bytes measured) so it is valid for pixel-diff fidelity too. LIVE is written only by the final delivery act; its correctness is guaranteed by construction because preview renders exactly the EDIT state that will be published. This keeps the entire pipeline off the publication/LIVE path — the path that corrupted this run.

15. **Images are WEAKREFERENCE** — upload to DAM first, then reference by UUID. Never store image URLs as strings in content.

16. **Absolute areas (header, footer) are created once** at `/sites/{siteKey}/home/header` and `footer`. Never drop them as regular page components.

## Mixins

17. **Extract shared fields into mixins before writing the second content type.** Common: `nsmix:cta` (link + label), `nsmix:media` (image + alt), `nsmix:badge` (label + color), `nsmix:seo` (metaTitle + metaDesc).

## Local mirror & analyze pipeline (learned on the 5 reference sites)

18. **Never trust static asset discovery alone.** JS-composed URLs (Liferay AMD/combo loader, Next.js `/_next/static/*` chunk maps) only surface when a real browser renders the mirror — the `mirror_probe` runtime-repair fixpoint captures them into `runtime-manifest.json`. Never skip or bypass the mirror gate before the fidelity gate.

19. **Never fetch scrape-detection or consent hosts during repair.** contentful.com embeds `canarytokens.com` beacons that exfiltrate the requesting URL — fetching one FIRES it. The tracker blocklist in `mirror_net.mjs` (canarytokens, osano, onetrust, trustarc…) is a security boundary, not an optimization.

20. **Charset is a silent fidelity killer.** Rewritten `<head>` can push `<meta charset>` past the browser's 1024-byte sniff window → Latin-1 mojibake → ~9 pixel-fidelity points lost (measured on supercar). The localizer injects `<meta charset="utf-8">` first in head and mirror servers send explicit `; charset=utf-8`. Any new artifact-serving path must do the same.

21. **Judge the component model editorially at the model gate, not just structurally.** Hash-suffixed type names (`ctf:callToActionCard9pqm4`), bare tags (`lfr:div`), or leaked layout classes (`lgColSpan8`, `lfrLayoutStructureItemSection`) mean the grouping failed editorially even if every gate is green. Expect: SXA → clean names; Next.js → good structure/bad names; Liferay-class layout markup → anemic model needing altitude tuning.

## Contribution model — the migration must be USABLE by a CMS editor (P2.5, learned on acquia/supercar/contentful)

The fidelity gate (pixels) and the JCR state can both be green while the migration is still **uneditable in practice**. Three review rounds all lived in that blind spot. The rules below are what made it contributable; the gates that enforce them are G1/G5/G6 (see ANALYZE-PIPELINE).

22. **A promoted section is a SKELETON + lifted fields, never a WYSIWYG blob.** The node stores its own captured markup (hidden `skeleton` prop) with `{{f:title}}`/`{{f:body*}}`/`{{media:imageN}}`/`{{link:href}}`/`{{child:N}}` markers; the view substitutes current property values. Rendering an unedited node is byte-identical to the source; every edit reflows into the same markup. Never load a section as one richtext field holding aggregated HTML — that is the "not how a CMS works" failure Julian flagged.

23. **Lift fields by DOM markers, never by string search.** `make_skeleton`'s value-in-HTML string match produced 59/62 DEAD props (the prop loads but editing it changes nothing). `semantic_extract.decompose_group` places markers on the source ELEMENT in the tree, so a field that can't be placed is simply NOT loaded (and counted) — dead props become structurally impossible. Every skeleton self-checks: `recompose_group(skeleton, fields, children)` must equal the original byte-for-byte, or the group falls back to verbatim `rawHtml` (fidelity before contribution).

24. **Repeated sibling items become CHILD NODES, not one monolith.** A container's repeated same-signature children (`>=3`) are lifted to typed `item-N` child nodes (each its own skeleton + `title`/`body*` fields), spliced back via `{{child:N}}`. BUT repeated `<p>`/`<h*>`/`<ul>` are a text RUN (one richtext body), never items — treating them as items made a Next.js article 10 near-empty nodes.

25. **Editor fields ride PER-NODE slot mixins, never type-level props.** Declaring `body..bodyN`/`imageN`/link on the TYPE sizes every node's edit form to the RICHEST instance → lean nodes show empty unjustified `body2`/`body3` fields (Julian's 2nd review). Instead the type declares only the hidden `skeleton`; each editor field is a module mixin (`nsmix:contribBody[N]`, `nsmix:contribImage[N]` + hidden `imageNOrig`/`imageNOrigRef`, `nsmix:contribLink`, plus `mix:title`) the LOADER adds per node (create → `addMixins` via GraphQL → set props → weakrefs → publish). The form then shows EXACTLY the fields that node carries. This is the `jmix:externalLink` pattern applied to every slot.

26. **Media = weakreference to a DAM copy, with a verbatim-default contract.** Each image unit gets `imageN` (weakref, picker[type='image']) + hidden `imageNOrig` (exact source markup) + `imageNOrigRef` (UUID of the DAM copy of the original). The view renders `imageNOrig` VERBATIM while `weakref UUID == origRef` (byte-exact default — fidelity safe by construction); once an editor picks another image, the chosen one wins (`<source>`/srcset dropped, `<img src>` swapped). Upload via MCP `media.upload.create`→PUT→`finalize`, dedupe map committed to `orchestration/images/<project>.dam.json`.

27. **The FIRST residue link per node is the contributor link; the rest stay verbatim.** `j:linkType`/`linkLabel`/hidden `linkOrig` on the node (j:linkType is a node-level singleton). Loader: external → `jmix:externalLink` + `j:url`; internal that maps to a MIGRATED page → `jmix:internalLink` + `j:linknode`; unresolvable internal → `linkOrig` verbatim fallback (rendered byte-exact, editor can rewire). j:url/j:linknode are mixin-injected — NEVER in the CND.

28. **In EDIT mode, item children render through the Jahia pipeline (`<Render node>`), not string-composed.** A correct Content Editor form is useless if the card has no clickable edit FRAME in Page Builder (Julian's 3rd review — "je ne peux toujours pas éditer ce bloc"). LIVE keeps the byte-exact string composition; EDIT/PREVIEW interleaves `<Render>` per item. Deeply-nested `{{child:N}}` that the recursion can't place are still appended via `<Render>` so every item is always reachable (G6 guarantee).

29. **Text inside script-driven widgets is NOT contributor content.** The G1 denominator excludes `<form>`/`<button>`/`<select>`/`<textarea>`/`<video>`/`<iframe>` subtrees (webforms, filter panels). The probe prints raw AND widget-excluded; the gate judges widget-excluded.

## Fidelity truths for real visitors (P3, learned on supercar/contentful/discoverasr)

30. **Crawl the POST-HYDRATION DOM, not the raw HTTP response.** `crawl-site.py` renders each page in a browser (`render_page.mjs`: network-idle + scroll-to-bottom + MutationObserver quiescence) and captures `document.documentElement.outerHTML` — what a VISITOR sees. UNIFORM: every page is rendered, no "is this a SPA" branch (a server-rendered page's post-JS DOM ≈ its HTML), so there is nothing to overfit. Measured: discoverasr home 400 KB/3785 visible chars (raw) → 1.5 MB/26 295 chars (rendered, 7× content); generalises to unseen SPAs (vercel +44 %, notion +82 %). Do NOT freeze Date/rAF during render — it breaks framework init (805 KB→28 KB); render faithfully and normalise the output instead. The captured snapshot does NOT re-hydrate-wipe offline (content survives with the API blocked), so no script neutralization is needed.

30b. **Lazy images: even rendered DOM references them in `data-src` only** (the site's JS swaps to `src` on scroll — JS that runs in neither the offline mirror nor the JS-stripped Jahia render). `localize_site` materialises `data-src`/`data-srcset` into `src`/`srcset` (measured: discoverasr 10→52→all images). Any image referenced only in a data-attr is invisible to a real visitor unless materialised.

31. **Rewrite runtime/CDN asset URLs in EVERY form.** Markup references the same asset as `https://host/path`, `//host/path` (protocol-relative), or `/path`; the runtime-manifest keys one form. Register all forms or the others stay un-rewritten → broken for real visitors (contentful CDN logos, discoverasr absolute paths). Never assume the captured HTML uses the same URL form as the manifest.

32. **Comments carry layout meaning — serialize them WITH their markers.** bs4 `str(Comment)` yields bare text; the shell recomposition must re-wrap `<!-- -->` or comment text (GTM markers, `#wrapper`) renders VISIBLY on the page.

33. **Client-rendered SPAs ARE now accepted — the render-crawl (rule 30) materialises their content.** discoverasr (AEM SPA, main content via XHR) went from "blocked at the mirror gate, 5.6%" to "0 ext-miss / 0 local-404 on every page, fully rendered offline" once the crawl rendered the post-hydration DOM. The remaining HONEST boundary is narrower: content that is NOT deterministically materialisable even by a render+scroll — auth-gated, per-user personalized, or infinite-scroll with no canonical end. Those still fail the mirror gate (mirror-fidelity stays low because the two captures differ run-to-run), and refusing them is correct. The line is drawn by the gate objectively, not by "is it a SPA".

34. **WAF/anti-bot runtime beacons are ignorable, not localize holes.** Imperva/Incapsula inject same-origin `_Incapsula_Resource?SWKMTFSR=` beacons (random query each load) that 404 offline correctly. `mirror_probe`'s `WAF_BEACON` path pattern (Incapsula, Cloudflare `/cdn-cgi/`, Akamai `/akam/`, PerimeterX) excuses them — same class as the scrape-detection blocklist (rule 19). Never fetch/repair them.

35. **Mirror-fidelity (offline-vs-live pixel %) is NOISY on live marketing sites** — rotating hero carousels, consent banners in different states, and time-varying content mean two screenshots taken moments apart never match well (discoverasr sits ~8% even when the offline render is visually perfect). Mirror-fidelity is a REPORTED metric, not the hard gate; the hard gate is "renders fully offline (0 miss/404, styled)". The deterministic pixel judge is the GROUND-TRUTH gate (deployed Jahia vs the SAME frozen mirror snapshot), never offline-vs-live.
