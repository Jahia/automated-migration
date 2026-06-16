# jahiaMigration — Skill Map

This harness migrates existing websites to Jahia JavaScript modules. Skills are numbered by workflow order.

---

## Migration workflow (numbered steps)

| # | Skill folder | Command | Purpose |
|---|---|---|---|
| 1 | `01-analyze-website/` | `/1-analyze` | Download + analyze site → component manifest |
| 2 | `02-scaffold-module/` | `/2-scaffold` | Scaffold Jahia JS module with `npm init @jahia/module@latest` |
| 3 | `03-import-assets/` | `/3-assets` | Copy CSS, JS, fonts, images into `static/` |
| 4 | `04-define-content-types/` | (part of step 5) | CND definitions + types.ts |
| 5 | `05-implement-navigation/` | (part of step 5) | MainNavigation 3-level JCR component |
| 6 | `06-implement-jcr-query/` | (part of step 5) | JCRQuery listing component |
| 7 | `07-implement-components/` | `/5-components` | All components via parallel subagents |
| 8 | `08-page-templates/` | `/4-templates` | Layout.tsx + AbsoluteArea + page variants |
| 9 | `09-create-content/` | `/6-content` | Create pages and content via GraphQL |
| 10 | `10-review/` | `/jahia-review` | CTO-level code review |
| 11 | `11-debug/` | `/jahia-debug` | Debug build/deploy/runtime errors |

**Entry point:** `/migration-workflow` orchestrates all steps.

---

## Supporting skills (migration helpers)

| Skill folder | Purpose |
|---|---|
| `support-create-view/` | Implement a React view (.server.tsx + CSS Module) |
| `support-deploy/` | Build + deploy module to local Jahia |

---

## JS/React development skills (`dev/`)

General Jahia JS module development — used during and after migration for building, reviewing, debugging.

| Skill | Purpose |
|---|---|
| `dev/jahia/` | Top-level GPS — start here if unsure what to do |
| `dev/jahia-dev/` | JS module GPS — detect project state, pick next step |
| `dev/jahia-dev-build-component/` | Build a complete component (CND + view) — shortcut |
| `dev/jahia-dev-create-template-set/` | Scaffold a new Jahia JS module from scratch |
| `dev/jahia-dev-create-view/` | Implement a React view (.server.tsx + CSS Module) |
| `dev/jahia-dev-define-content-type/` | Define a CND content type + types.ts |
| `dev/jahia-dev-import-from/` | Build a component from an external URL |
| `dev/jahia-dev-query-content/` | JCR-SQL2 queries and useJCRQuery listings |
| `dev/jahia-dev-accessibility/` | Audit live pages with axe-core, fix WCAG 2.1 AA |
| `dev/jahia-dev-screenshot/` | Screenshot reference + Jahia render for visual comparison |
| `dev/jahia-dev-start-local/` | Start Jahia locally (Docker or bare metal) |
| `dev/jahia-dev-cypress/` | Scaffold Cypress e2e tests for components |
| `dev/jahia-dev-properties/` | JCR properties reference |
| `dev/jahia-dev-apis/` | REST and GraphQL API reference |
| `dev/jahia-dev-jexperience/` | jExperience personalization integration |
| `dev/jahia-dev-ops/` | Operations and provisioning |
| `dev/jahia-dev-ui-extension/` | OSGi UI extension from JS module |

---

## OSGi/Java skills (`osgi/`)

For back-office extensions and Java service bundles. Distinct from JS template sets.

| Skill | Purpose |
|---|---|
| `osgi/jahia-osgi-module/` | Maven bundle structure, DS annotations, JCR integration |
| `osgi/jahia-osgi-ui-extension/` | Webpack/Module Federation, React 18, registry, actions, dialogs |
| `osgi/jahia-dev-osgi-module/` | OSGi module development conventions |

---

## Content management skills (`content/`)

For creating, querying, and managing JCR content on a running Jahia instance.

| Skill | Purpose |
|---|---|
| `content/jahia-content/` | GPS — detect site state, route to content operation |
| `content/jahia-content-explore-structure/` | Map content types, properties, enums on an unknown site |
| `content/jahia-content-query-content/` | List and inspect content via GraphQL |
| `content/jahia-content-move-content/` | Restructure the content tree |
| `content/jahia-content-translate-content/` | Translate nodes to a new language and publish |

---

## Context documents

Loaded by agents when relevant. Do not modify without reason.

| File | Purpose |
|---|---|
| `context/jahia-platform.md` | Architecture: JCR, workspaces, OSGi, render pipeline |
| `context/jahia-development-guidelines.md` | CTO review standards — the bar all code must meet |
| `context/jahia-navigation-patterns.md` | MainNavigation + SiteHeader + 3-level nav pattern |
| `context/jahia-link-patterns.md` | linkTypeInitializer, j:linkType, buildNodeUrl |
| `context/jahia-i18n-patterns.md` | i18n file locations, useTranslation, loadNamespaces |
| `context/jahia-js-reference-patterns.md` | Production patterns from real modules |
| `context/jahia-frontend-backend-patterns.md` | Decision tree: 5 integration patterns with complete code |
| `context/jahia-graphql-schema-reference.md` | GraphQL schema: JCRQuery, JCRMutation, JCRNode, all types |
| `context/jahia-cnd-syntax-reference.md` | CND syntax, property types, constraints |
| `context/jahia-selectortype-pattern.md` | Custom content editor widgets (SelectorType) |
| `context/jahia-taxonomy-patterns.md` | Tags (jmix:tagged) and categories (category weakreference) |
| `context/jahia-accessibility-patterns.md` | WCAG 2.1 AA patterns for Jahia components |
| `context/jahia-seo-patterns.md` | SEO meta, og:tags, structured data |
| `context/javascript-modules-library-api.md` | @jahia/javascript-modules-library API reference |

---

## How skills work

- Each skill is a `SKILL.md` file in its numbered folder
- Skills are invoked by slash command (e.g. `/1-analyze`) or referenced by agents
- Skills are step-by-step guides with code examples, validation checklists, and gotchas
- Context documents are loaded on demand — agents read them when the task needs that knowledge
