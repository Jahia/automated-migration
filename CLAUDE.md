# jahiaMigration — Jahia Website Migration Harness

This is the canonical harness for **migrating existing websites to Jahia JavaScript modules**. It combines migration workflow commands with Jahia's complete JS module development skill set.

---

## What this repo does

Given a website URL (or HTML/screenshots), this harness guides you through:

1. Analyzing the site and mapping it to Jahia components
2. Scaffolding a new Jahia JS module (React 19, Vite)
3. Importing static assets (CSS, JS, fonts, images)
4. Implementing page templates (Layout, AbsoluteArea, page variants)
5. Implementing all components (CND + TSX + CSS + resource bundles)
6. Creating content via GraphQL API

Run `/migration-workflow` to start. It orchestrates everything.

---

## The agentic harness pattern

This repo follows the `.agents/` harness pattern. All skills, context, and agents are in:

```
.agents/
├── README.md           # Skill map and step-by-step index
├── context/            # Reference docs (platform, patterns, APIs)
└── skills/             # Step-by-step guides, numbered by workflow position
    ├── 01-analyze-website/
    ├── 02-scaffold-module/
    ├── 03-import-assets/
    ├── 04-define-content-types/
    ├── 05-implement-navigation/
    ├── 06-implement-jcr-query/
    ├── 07-implement-components/
    ├── 08-page-templates/
    ├── 09-create-content/
    ├── 10-review/
    └── 11-debug/
```

Skills are numbered by migration workflow order. Invoke them by name (e.g. `/jahia-dev-define-content-type`) or let `/migration-workflow` sequence them.

---

## Module type

All migrations produce a **Jahia JavaScript module** (Track 1):

| Property | Value |
|---|---|
| React version | **19** |
| Build tool | Vite |
| Deployment | tgz -> OSGi bundle |
| Scaffolding | `npm init @jahia/module@latest` |

Never use React 18 APIs. Never target OSGi/Java bundles here — this harness is JS/React only.

---

## Non-negotiable rules

### All tracks

1. **Never escalate to a system JCR session** for content the calling user authored.
2. **Publication is a SINGLE FINAL act, never during the process (Julian, 2026-07-04).** The migration process is EDIT-only: never publish per-node/per-area during loads or probes — a stale LIVE is tolerated and expected. Per-node publication during loads corrupted the publication metadata (a naive `publish` then no-ops in 1 ms while LIVE stays stale; measured: 18 005 jobs). Publish once at the end via `orchestration/assist/publish_site.sh <project> <site>` (unpublish-first). "Always publish after JCR mutations" applies to that FINAL act only. See `.claude/rules/migration.md` §14.
3. **Always include `-H "Origin: $JAHIA_URL"`** in GraphQL curl requests — the Origin must match `$JAHIA_URL` exactly (it is port-sensitive).
4. **All modules ship EN and FR at minimum.** See `.agents/context/jahia-i18n-patterns.md`.

### JS template sets

5. **Never use `yarn dev` from an agent.** Always use `yarn build && yarn jahia-deploy`.
6. **Never hardcode UI strings in views** — use `t("key")` from `useTranslation()`.
7. **Never hardcode links or URLs** in views or templates. All navigable links come from contributed content.
8. **Never use `jmix:studioOnly`** on structural types — use `jmix:hiddenType`.
9. **Never declare `j:linknode` or `j:url` in a CND** — they are injected by Jahia's mixins when using `linkTypeInitializer`.
10. **Never declare `jcr:title` in CND** — use `mix:title` as a supertype.
11. **Any mixin that stores hidden child nodes must declare `+ childName (Type) = Type version`** in the mixin body. Without this, `session.addNode()` throws `ConstraintViolationException` at runtime.
12. **Keep all locale JSON files in sync** (`fr.json`, `en.json`). A key missing in one file renders as raw key.

### Migration-specific rules

13. **Navigation must go 3 levels deep via a Jahia Navigation Menu component.** Never build hardcoded nav links or plain `<a>` lists. Use `getChildNodes` on the home page for level 1, level-1 children for level 2, level-2 children for level 3. See `.agents/context/jahia-navigation-patterns.md`.

14. **Use `linkTypeInitializer` for every contributor-facing link.** Any CTA, banner link, card link, footer link, or nav fallback item must use `j:linkType (string, choicelist[linkTypeInitializer])` in the CND. Never store a URL in a plain `string` field.

15. **Never create CND properties for Tags or Categories.** Use Jahia's built-in capabilities:
    - Free-form tags: extend `jmix:tagged` (injects `j:tagList`)
    - Taxonomy categories: use `(weakreference, category[autoSelectParent=false]) multiple`

16. **Every migrated module ships a JCRQuery and GridRow component** adapted to the module namespace. These are the primary tools editors use to build listing pages without developer help.

17. **Design for mixin reuse from the start.** Before writing a second content type, extract shared property groups into module-level mixins in `settings/definitions.cnd`. Common patterns: `nsmix:cta`, `nsmix:media`, `nsmix:badge`, `nsmix:seo`.

18. **Every resource bundle field key must have a companion `ui.tooltip` key.** No field in `.properties` files is complete without its tooltip.

```properties
ns_hero.title=Title
ns_hero.title.ui.tooltip=Main heading displayed at the top of the hero section.
ns_hero.j:linkType=Call to Action
ns_hero.j:linkType.ui.tooltip=Link for the primary CTA button. Choose internal page or external URL.
```

19. **Accessibility is mandatory** — every component must pass WCAG 2.1 AA. Run `/jahia-dev-accessibility` after implementing each component.

---

## Migration workflow commands

| Command | Step | What it does |
|---|---|---|
| `/migration-workflow` | All | Orchestrates the complete 6-step migration |
| `/1-analyze` | 1 | Download + analyze the source website |
| `/2-scaffold` | 2 | Create the Jahia JS module with scaffolding tool |
| `/3-assets` | 3 | Import CSS, JS, fonts, images into `static/` |
| `/4-templates` | 4 | Implement Layout.tsx, AbsoluteArea, page templates |
| `/5-components` | 5 | Implement all components in parallel (CND + TSX + CSS) |
| `/6-content` | 6 | Create pages and content via GraphQL |

---

## Supporting commands

| Command | Purpose |
|---|---|
| `/jahia-review` | CTO-level code review before shipping |
| `/jahia-debug` | Debug build/deploy/runtime errors |
| `/jahia-deploy` | Build and deploy to local Jahia |
| `/jahia-i18n-check` | Verify all locale files are in sync |

---

## Quality gates (the migration is trustworthy iff these are green)

A migration is not "done" when it renders — it is done when it renders faithfully AND a
CMS editor can contribute. Run these in order; each has a probe that exits non-zero to block.
Full detail in `orchestration/ANALYZE-PIPELINE.md` §3; contribution rules in `.claude/rules/migration.md` §22-33.

| Gate | Probe | Asserts |
|---|---|---|
| Mirror | `mirror_probe.mjs` | page renders fully offline (client-rendered SPAs correctly REFUSED) |
| Fidelity / Ground truth | `probes/groundtruth.sh <proj> <site> 99` | deployed Jahia page ≥99% pixel-identical to the source mirror, per page |
| **G1 contribution** | `probes/contribution.py <proj>` | editable-text coverage ≥60%/85%; **0 dead props / phantom / empty shells** |
| **G5 media/links** | `probes/contribution.py <proj>` | ≥90% media → DAM weakref; ≥95% links → j:linkType |
| **G6 editor surface** | `probes/editor-surface.py <proj> <site>` | every wired prop is rw in `forms.editForm`; every item has a Page Builder edit frame |
| **G2 round-trip** | `probes/roundtrip.py <proj> <site>` | sentinel edits reach LIVE and restore |

The full loop is generated by `gen_plan.py --segmentation vision` (default) and run by
`run_plan.py`. Pixel fidelity NEVER proves editability — G1/G2/G6 are what make a
migration usable, and they were added after three review rounds where a pixel-perfect
site was still uneditable (`forms.editForm` is the truth source for what an editor sees).

---

## Tooling URLs (local dev)

URLs and credentials come from the repo-root `.env.local` (gitignored — copy `.env.example` and adjust). On THIS machine Jahia runs on **http://localhost:8081** with `root` / see `.env.local` (`docker/docker-compose.yml` maps `8081:8080`); port 8080 may be a different, unrelated service — a `{"detail":"Not Found"}` answer there is NOT a Jahia auth problem. Always `source .env.local` and use the variables:

| Tool | URL |
|---|---|
| Jahia UI | `$JAHIA_URL` - credentials: `$JAHIA_USER` / `$JAHIA_PASS` |
| GraphQL playground | `$JAHIA_URL/modules/graphql` |
| JCR browser | `$JAHIA_URL/modules/tools/jcrBrowser.jsp` |
| Installed definitions | `$JAHIA_URL/modules/tools/definitionsBrowser.jsp` |

---

## Further reading

- `.agents/README.md` - Full skill map
- `.agents/context/jahia-navigation-patterns.md` - Navigation with 3 levels
- `.agents/context/jahia-development-guidelines.md` - CTO review standards
- `.agents/context/jahia-platform.md` - Architecture cheat sheet
- `.agents/context/javascript-modules-library-api.md` - JS API reference
- Jahia academy: https://academy.jahia.com/tutorials-get-started/front-end-developer
