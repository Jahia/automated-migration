---
description: Complete Jahia website migration from URL to populated site
---

Orchestrates the complete 6-step migration pipeline for recreating an existing website in Jahia.

## Complete Workflow

### Step 1: Analyze Website
Download and analyze the target website to identify components, templates, and content structure.

**Command:** `/1-analyze`

**Provide:** Website URL, screenshot, or HTML files

**Output:**
- `workflow-output/analysis.md` — component specifications with HTML fragments
- `workflow-output/component-manifest.json` — structured component list with fields and flags
- `workflow-output/content-data.json` — actual content extracted from the site
- `workflow-output/asset-inventory.json` — all images and media catalogued by section

---

### Step 2: Scaffold Jahia Module
Bootstrap a new Jahia JavaScript module using the official scaffolding tool.

**Command:** `/2-scaffold`

**Output:** Ready-to-use Jahia module at `projects/<module-name>/`

---

### Step 3: Import Website Assets
Copy all static assets (CSS, JavaScript, images, fonts) from the downloaded site into the module.

**Command:** `/3-assets`

**Output:** Organized `static/` folder + Layout.tsx wired to assets

---

### Step 4: Implement Template Set
Set up Layout.tsx with AbsoluteArea for header/footer, page template variants, and the MainResource template.

**Command:** `/4-templates`

**Output:** Complete template set with header/footer areas and page variants

---

### Step 5: Implement Components
Generate all component files (CND, TSX, CSS, resource bundles) using parallel subagents.

**Command:** `/5-components`

**What happens:**
- One subagent per component, all running simultaneously
- Each creates: `definition.cnd`, `default.server.tsx`, `component.module.css`, resource bundle entries
- Containers use `+ * (namespace:childType)` — never `jmix:list`
- Navigation component reads from JCR tree — never hardcoded links
- After agents complete: deduplication, resource bundle check, build verification

**Output:** All component files + successful `yarn build`

---

### Step 6: Create Content
Create pages and content via Jahia GraphQL API.

**Command:** `/6-content`

**What happens (in order):**
1. Upload images to DAM
2. Create absolute area content (header, footer)
3. Create home page components in `main` area
4. Create content folders and items
5. Create sub-pages with content
6. Publish everything including translation nodes

**Output:** Fully populated site in LIVE workspace

---

## Execution Instructions

### Determine starting point

**If URL provided (e.g. `/migration-workflow https://example.com`):**

1. List `projects/` for any existing module for this site
2. If none exists: tell user "No module found — starting from Step 1" → invoke `/2-scaffold` → set PROJECT_PATH → invoke `/1-analyze`
3. If module exists: identify PROJECT_PATH, ask user which step to continue from

**If no argument:**

Ask user:
1. Run complete workflow for a new website
2. Start with analysis only (`/1-analyze`)
3. Scaffold a module (`/2-scaffold`)
4. Import assets (`/3-assets`)
5. Implement components from existing specs (`/5-components`)
6. Create content (`/6-content`)

### Quality gates (check after each step)

**After /1-analyze:**
- Verify 4 files exist in `workflow-output/`
- Count `componentInstances` and `children` in content-data.json
- Warn if count seems low for the site complexity

**After /3-assets:**
- Count files in `static/css`, `static/js`, `static/fonts`, `static/assets`
- Verify Layout.tsx references inline.css and inline.js

**After /4-templates:**
- Verify Layout.tsx contains `<AbsoluteArea>` for header and footer
- Verify `src/templates/Page/basic.server.tsx` exists
- Verify `src/templates/MainResource/default.server.tsx` exists if any component has `needsFullPage: true`

**After /5-components:**
- Verify `settings/resources/<module>.properties` has entries for every component
- Verify components with `needsFullPage: true` have `default.server.tsx` AND `fullPage.server.tsx`
- Verify `yarn build` succeeds with no errors

**After /6-content:**
- Curl LIVE home page and verify non-empty text content
- Curl each sub-page and verify HTTP 200
- Count items in rendered HTML vs content-data.json

---

## Quick reference

| Command | Purpose |
|---|---|
| `/1-analyze [url]` | Download + analyze site |
| `/2-scaffold` | Create Jahia module |
| `/3-assets` | Import static assets |
| `/4-templates` | Set up Layout + templates |
| `/5-components` | Implement all components |
| `/6-content` | Create pages and content |

---

## Terminology

- **Analyze** = examine website and map to Jahia component types
- **Scaffold** = create a new Jahia JS module project with `npm init @jahia/module@latest`
- **Import** = copy static assets (CSS, JS, images, fonts) into project
- **Implement** = write component code (CND, TSX, CSS, properties)
- **Build** = compile with Vite (`yarn build`)
- **Deploy** = upload module to Jahia (`yarn jahia-deploy`)
- **Create** = add pages/content via GraphQL API
