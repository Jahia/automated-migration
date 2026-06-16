---
description: Complete Jahia website migration from URL to populated site
type: workflow
status: active
invokes_workflow: true
sub_skills:
  - 1-analyze-website
  - 2-scaffold-module
  - 3-import-assets
  - 4-define-content-types
  - 5-implement-navigation
  - 6-implement-jcr-query
  - 7-implement-components
  - 8-page-templates
  - 9-create-content
  - 10-review
---

## Agent identity
- **Agent name:** Conductix
- **Reference style:** Orchestra / conducting
- **Signature line (en):** *"Six agents. One site. Trust the pipeline."*
- **Personality note:** Systematic and patient. Coordinates all sub-agents, narrates each handoff, and stops at all 5 human validation gates. Never skips a gate to save time.
- **Usage rule:** Brief invocation only in step transitions. Never appears in deliverables.

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

### Step 5.5: Validate Module (MANDATORY — cannot skip)

**Command:** `/validate-module`

This is a non-negotiable gate. The module MUST pass all checks before any site or content work begins.

**What it checks:**
1. **CND syntax** — no invalid JCR types (`richtext`, `text`, `int` are all wrong; use `string`/`long`/`double`)
2. **Namespace conflict** — queries live Jahia to detect any `prefix already declared` or `uri already declared` conflict BEFORE uploading. A namespace stuck in the JCR registry from a previous failed deploy will silently prevent CND registration even when the upload says "Operation successful".
3. **Build** — `yarn build` must exit 0
4. **Deploy** — `yarn jahia-deploy` must succeed
5. **Module ACTIVE** — the OSGi bundle must reach ACTIVE state (not just INSTALLED or RESOLVED)
6. **Types queryable** — at least one module CND type must be queryable via GraphQL (`SELECT * FROM [ns:type]` must not return "node type does not exist")

**If ANY check fails: STOP. Fix the issue. Re-run `/validate-module` from the top.**

Do NOT proceed to step 6 until `/validate-module` prints "ALL VALIDATION CHECKS PASSED".

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

## State & Logging Protocol

Every step reads and writes two persistent files inside `$PROJECT_PATH/workflow-output/`:

### `state.json` — migration state machine

Format:
```json
{
  "siteUrl": "https://example.com",
  "projectPath": "projects/module-name",
  "moduleName": "module-name",
  "namespace": "ns",
  "startedAt": "2026-06-16T14:00:00Z",
  "steps": {
    "1-analyze":   { "status": "completed", "completedAt": "...", "notes": "12 components, 87 instances" },
    "2-scaffold":  { "status": "completed", "completedAt": "..." },
    "3-assets":    { "status": "pending" },
    "4-templates": { "status": "pending" },
    "5-components":{ "status": "pending" },
    "6-content":   { "status": "pending" }
  }
}
```

Status values: `pending` | `in_progress` | `completed` | `failed`

**Rules:**
- Create `state.json` when scaffolding the module (step 2), or at the start of step 1 if analysis runs first.
- At the **start** of every step: read `state.json`, set the step's status to `in_progress`, write the file.
- At the **end** of every step: set status to `completed` (or `failed`), add notes with key counts, write the file.
- If a step fails mid-way, set status to `failed` with an error note — do not leave it as `in_progress`.

### `migration-log.md` — append-only human-readable log

Append one entry after each step completes or fails:

```markdown
## [2026-06-16 14:32] Step 1 — Analyze Website
- **Status:** COMPLETED
- **Outputs:** analysis.md (450 lines), component-manifest.json (12 components), content-data.json (87 instances, 43 children), asset-inventory.json (143 images)
- **Gate result:** PASS — all 4 files present, counts above threshold
- **Notes:** Site uses Owl Carousel. 3 desktop + 2 mobile-only components identified.
```

For failures:
```markdown
## [2026-06-16 14:45] Step 3 — Import Assets — FAILED
- **Error:** wget returned 403 for CSS URLs
- **Action taken:** Downloaded CSS manually via curl with auth header
- **Resolution:** Resumed with 4 CSS files + 2 JS files imported
```

---

## Execution Instructions

### Step 0: Collect Jahia server details (MANDATORY — before any work)

**Before doing anything else**, ask the user for the Jahia instance details. Do not assume defaults. Do not proceed until all three are provided.

Ask exactly:

```
Before we start, I need your Jahia server details:

1. Jahia URL (e.g. http://localhost:8080)
2. Username
3. Password
```

Once provided, store them in the session as:
- `JAHIA_URL` — base URL, no trailing slash
- `JAHIA_USER` — username
- `JAHIA_PASS` — password

Verify connectivity immediately:

```bash
HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Origin: $JAHIA_URL" \
  "$JAHIA_URL/modules/graphql")
echo "HTTP $HTTP"
```

- `200` or `400` → connected (400 = GraphQL endpoint reached, no query sent yet — that is fine)
- `401` → wrong credentials — ask again
- `000` or connection refused → wrong URL or Jahia not running — ask again

Do not proceed past this check until a `200` or `400` is returned.

Write `JAHIA_URL`, `JAHIA_USER` (only — never the password) into `state.json` under a `server` key for reference by subsequent steps.

---

### Determine starting point

**If URL provided (e.g. `/migration-workflow https://example.com`):**

1. List `projects/` for any existing module for this site
2. Check if `projects/*/workflow-output/state.json` exists with matching `siteUrl`
3. If **state.json found**: read it, report current step statuses, ask user which step to continue from
4. If **no state.json**: tell user "No module found — starting from Step 1" → invoke `/2-scaffold` → set PROJECT_PATH → invoke `/1-analyze`

**If no argument:**

Ask user:
1. Run complete workflow for a new website
2. Start with analysis only (`/1-analyze`)
3. Scaffold a module (`/2-scaffold`)
4. Import assets (`/3-assets`)
5. Implement components from existing specs (`/5-components`)
6. Create content (`/6-content`)

### Prerequisite enforcement (check before invoking each step)

**Before /1-analyze:** No prerequisites. Create `workflow-output/` if absent.

**Before /3-assets:**
- Verify `workflow-output/state.json` exists and `1-analyze.status == "completed"`
- Verify `workflow-output/asset-inventory.json` exists
- If not: STOP. Tell user step 1 must complete first. Do not proceed.

**Before /4-templates:**
- Verify `2-scaffold.status == "completed"` in state.json
- Verify `src/` directory exists in PROJECT_PATH
- If not: STOP.

**Before /5-components:**
- Verify `1-analyze.status == "completed"` AND `3-assets.status == "completed"` AND `4-templates.status == "completed"`
- Verify `workflow-output/component-manifest.json` exists and has `> 0` components
- If not: STOP. Report which prerequisite is missing.

**Before /6-content:**
- Verify `5-components.status == "completed"` in state.json
- Verify `5.5-validate.status == "completed"` in state.json (set by `/validate-module`)
- If either is missing: STOP. Tell user to run `/validate-module` first.
- DO NOT run `/6-content` until the module is confirmed ACTIVE and CND types are queryable.
- Creating a site before the module is valid wastes time — site template sets reference CND types that must exist first.

### Quality gates (check after each step, append to migration-log.md)

**After /1-analyze:**
- Verify 4 files exist in `workflow-output/`: analysis.md, component-manifest.json, content-data.json, asset-inventory.json
- Count `componentInstances` total and total `children` in content-data.json — report both numbers
- **HARD STOP if total instances < 5** — incomplete extraction. Re-run /1-analyze.
- **HARD STOP if any subPages[] entry has empty or missing `fields`** — sub-page content was not extracted. Run this check:
  ```bash
  cat workflow-output/content-data.json | python3 -c "
  import json,sys; data=json.load(sys.stdin)
  bad=[p['slug'] for p in data.get('subPages',[]) if not p.get('fields')]
  print('INCOMPLETE SUBPAGES:',bad if bad else 'NONE - OK')"
  ```
- Update state.json: `1-analyze.status = "completed"`, notes = "N components, M instances"
- **HUMAN GATE: Present the step summary from skill 01 and wait for user to type VALIDATED before proceeding.**

**After /2-scaffold:**
- Verify `src/components/`, `settings/definitions.cnd`, `package.json` exist
- Update state.json: `2-scaffold.status = "completed"`, add `moduleName` and `namespace` fields

**After /3-assets:**
- Count files in `static/css`, `static/js`, `static/fonts`, `static/assets` — report all 4 counts
- **HARD STOP if `static/css/` is empty** — no CSS was extracted. CSS must come from `/tmp/website-download/`, never fabricated.
- Verify Layout.tsx references at least one CSS file from static/
- Update state.json: `3-assets.status = "completed"`, notes = "N css, M js, P fonts, Q images"
- **HUMAN GATE: Report counts and CSS file names. Wait for user to type VALIDATED before proceeding to step 4.**

**After /4-templates:**
- Verify Layout.tsx contains `<AbsoluteArea>` for header and footer
- Verify `src/templates/Page/basic.server.tsx` exists
- Verify `src/templates/MainResource/default.server.tsx` exists if any component in manifest has `needsFullPage: true`
- Update state.json: `4-templates.status = "completed"`

**After /5-components:**
- Verify `settings/resources/<module>.properties` has entries for every component in the manifest
- Verify components with `needsFullPage: true` have both `default.server.tsx` AND `fullPage.server.tsx`
- Run `yarn build` — must exit 0. If it fails, set `5-components.status = "failed"` and STOP.
- Update state.json: `5-components.status = "completed"`, notes = "N components built"
- **HUMAN GATE: List all components built and whether yarn build passed. Wait for user to type VALIDATED before running /validate-module.**
- **After user confirms: immediately invoke `/validate-module`.** Do not wait for the user to ask — it is mandatory before step 6.

**After /validate-module:**
- All 6 checks must pass (CND syntax, namespace, build, deploy, ACTIVE state, types queryable)
- Update state.json: `5.5-validate.status = "completed"` (done by the skill itself)
- Only after this step can `/6-content` be invoked

**After /6-content:**
- Curl LIVE home page (`http://localhost:8080/sites/<siteKey>/home.html`) and verify non-empty text content
- Curl each sub-page from content-data.json and verify HTTP 200
- Count items in rendered HTML vs content-data.json — report match %
- Update state.json: `6-content.status = "completed"`
- **HUMAN GATE: Report LIVE URL, curl HTTP status, and a text excerpt from the home page. Wait for user to confirm the site looks correct.**

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
