# SKILLS.md — Routing Guide

This is the agent-facing routing guide. When a user describes what they want in natural language, find the matching skill below and invoke it.

---

## How to route

1. Read the user's request.
2. Find matching trigger phrases below.
3. Invoke the skill via its slash command or by reading its SKILL.md.
4. If in doubt: use `/jahia` (GPS) or `/migration-workflow` (full pipeline).

---

## Migration workflow triggers

### "Analyze / inspect / map the website"
→ **`$01-analyze-website`** (`/1-analyze`)

Triggers:
- "analyze this website"
- "map the components on this site"
- "what components does this site have"
- "extract the structure from this URL"
- "I want to migrate this site to Jahia"
- "scan this site"
- "what sections does this page have"

---

### "Set up / scaffold the Jahia module"
→ **`$02-scaffold-module`** (`/2-scaffold`)

Triggers:
- "scaffold the module"
- "create the Jahia module"
- "initialize the project"
- "set up the module structure"
- "create a new Jahia JS module"
- "npm init the module"

---

### "Import / copy the CSS, fonts, images, JS"
→ **`$03-import-assets`** (`/3-assets`)

Triggers:
- "import the assets"
- "copy the CSS files"
- "bring over the fonts"
- "download the site assets"
- "import the static files"
- "set up the static directory"

---

### "Define the content types / CND"
→ **`$04-define-content-types`** (`/jahia-dev-define-content-type`)

Triggers:
- "define the content types"
- "create the CND"
- "define the node types"
- "write the definitions.cnd"
- "create types.ts"
- "what fields should this component have"
- "model the content"

---

### "Build the navigation / header nav"
→ **`$05-implement-navigation`**

Triggers:
- "implement the navigation"
- "build the main nav"
- "create the navigation component"
- "set up the 3-level menu"
- "build the header navigation"
- "create the MainNavigation component"

---

### "Build the JCRQuery / listing component"
→ **`$06-implement-jcr-query`**

Triggers:
- "build the listing component"
- "create a JCRQuery component"
- "implement content listing"
- "build the card grid"
- "create a filterable list"
- "implement the blog listing"
- "build the GridRow component"

---

### "Build all the components"
→ **`$07-implement-components`** (`/5-components`)

Triggers:
- "implement all the components"
- "build the components"
- "create all the views"
- "implement the hero, cards, and footer"
- "build the site components"
- "implement everything"

---

### "Create the page templates / layout"
→ **`$08-page-templates`** (`/4-templates`)

Triggers:
- "create the page templates"
- "build the layout"
- "implement the Layout.tsx"
- "set up page variants"
- "create the AbsoluteArea header"
- "implement the page structure"

---

### "Create the content / populate the site"
→ **`$09-create-content`** (`/6-content`)

Triggers:
- "create the content"
- "populate the site"
- "add pages and content"
- "create the articles"
- "import the content"
- "set up the pages in Jahia"
- "create JCR nodes"

---

### "Review the code"
→ **`$10-review`** (`/jahia-review`)

Triggers:
- "review the code"
- "check for issues"
- "code review"
- "CTO review"
- "what's wrong with this"
- "validate the implementation"
- "run the review checklist"

---

### "Debug / fix the error"
→ **`$11-debug`** (`/jahia-debug`)

Triggers:
- "it's not working"
- "debug this error"
- "the component is not rendering"
- "build is failing"
- "deploy failed"
- "I see an error in the logs"
- "the content type is missing"

---

## Full pipeline

### "Migrate this site / run the full migration"
→ **`$migration-workflow`** (`/migration-workflow`)

Triggers:
- "migrate this site to Jahia"
- "run the full migration"
- "start the migration workflow"
- "migrate [URL] to Jahia"
- "run the whole pipeline"

---

## JS/React development triggers

| User says | Skill |
|-----------|-------|
| "I don't know where to start" | `dev/jahia` — GPS |
| "build me a component" | `dev/jahia-dev-build-component` |
| "create a new template set from scratch" | `dev/jahia-dev-create-template-set` |
| "implement the view for this component" | `dev/jahia-dev-create-view` |
| "write a JCR query" | `dev/jahia-dev-query-content` |
| "audit for accessibility issues" | `dev/jahia-dev-accessibility` |
| "compare the visual output" | `dev/jahia-dev-screenshot` |
| "start Jahia locally" | `dev/jahia-dev-start-local` |
| "add Cypress tests" | `dev/jahia-dev-cypress` |
| "build a component based on this URL" | `dev/jahia-dev-import-from` |

---

## OSGi/Java triggers

| User says | Skill |
|-----------|-------|
| "build an OSGi bundle" | `osgi/jahia-osgi-module` |
| "add a back-office action / dialog" | `osgi/jahia-osgi-ui-extension` |
| "write a Java Action" | `dev/jahia-dev-java` |

---

## Content management triggers

| User says | Skill |
|-----------|-------|
| "I don't know the state of the content" | `content/jahia-content` — GPS |
| "show me what content types are deployed" | `content/jahia-content-explore-structure` |
| "list the articles / pages / nodes" | `content/jahia-content-query-content` |
| "move or rename content" | `content/jahia-content-move-content` |
| "translate content to French" | `content/jahia-content-translate-content` |

---

## Governance

- `_references/migration-quality-bar.md` — the bar every task must meet
- `_references/human-validation-gates.md` — when to stop and ask the user
- `_references/skill-creation-governance.md` — how to add skills
