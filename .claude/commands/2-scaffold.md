---
description: Scaffold a new Jahia JavaScript module using the official scaffolding tool
---

## State management (run at start and end)

**At the START of this step:**
- No prerequisites for step 2.
- Create `projects/workflow-output/` if it doesn't exist yet (it will move into the module after scaffolding).

**At the END of this step (after yarn install completes):**
```bash
# 1. Verify scaffold succeeded
ls "$PROJECT_PATH/"{src,settings/definitions.cnd,package.json}

# 2. Create workflow-output/ inside the new module
mkdir -p "$PROJECT_PATH/workflow-output"

# 3. Create state.json
cat > "$PROJECT_PATH/workflow-output/state.json" << EOF
{
  "siteUrl": "<URL>",
  "projectPath": "$PROJECT_PATH",
  "moduleName": "<module-name>",
  "namespace": "<namespace>",
  "startedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "steps": {
    "1-analyze":    { "status": "pending" },
    "2-scaffold":   { "status": "completed", "completedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" },
    "3-assets":     { "status": "pending" },
    "4-templates":  { "status": "pending" },
    "5-components": { "status": "pending" },
    "6-content":    { "status": "pending" }
  }
}
EOF

# 4. Create migration-log.md
cat > "$PROJECT_PATH/workflow-output/migration-log.md" << EOF
# Migration Log — <module-name>
Site: <URL>
Started: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

## [$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Step 2 — Scaffold Module — COMPLETED
- **Module:** $PROJECT_PATH
- **Namespace:** <namespace>
EOF
```

If scaffolding fails: append FAILED entry to migration-log.md and stop.

---

Bootstrap a new Jahia JavaScript module as a subdirectory inside `projects/`.

## Instructions

### Step 1: Gather module details

Ask the user for:

| Field | Guidance |
|---|---|
| Module name | kebab-case matching the project (e.g. `carnival-demo`) |
| Namespace | Short prefix for content types (e.g. `carnival`) |
| Display name | Human-readable name shown in Jahia Studio |
| Jahia version | Use `8.2` unless instructed otherwise |

Confirm before proceeding.

### Step 2: Create the module

The scaffolding tool uses `@clack/prompts` — requires TTY, use `expect`:

```bash
mkdir -p projects/
cd projects/

expect -c "
  spawn npm init @jahia/module@latest <module-name>
  expect \"name of your module\"
  send \"\r\"
  expect \"Where do you want\"
  send \"\r\"
  expect \"module type\"
  send \"\x1B\[B\r\"
  expect eof
"
```

`\x1B\[B` = down-arrow to select "Empty template set" (option 2).

**Fallback if `expect` unavailable:** Ask user to run interactively and let you know when done.

### Step 3: Verify structure

Confirm these exist:
```
projects/<module-name>/
├── src/components/
├── settings/
│   ├── definitions.cnd
│   └── locales/
├── docker/provisioning.yml
├── package.json
├── vite.config.ts
└── docker-compose.yml
```

### Step 4: Install dependencies

```bash
cd projects/<module-name>
yarn install
```

### Step 5: Configure environment

Create `.env` if missing:
```env
JAHIA_USER=root:root
JAHIA_HOST=http://localhost:8080
```

### Step 6: Add shared CND foundations

Add these shared types to `settings/definitions.cnd` before any component implementation:

```cnd
// Module mixin — all components extend this, never jmix:droppableContent directly
[<namespace>Mix:component] > jmix:droppableContent, jmix:accessControllableContent mixin
[<namespace>Mix:pageComponent] > <namespace>Mix:component mixin  // for page Areas only

// Link mixin — for any component with a contributor-facing link
// j:url and j:linknode MUST be declared here (linkTypeInitializer is UI-only)
[<namespace>:linkTo] mixin
 - j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
 - j:url (string) indexed=no
 - j:linknode (weakreference) < jmix:mainResource, jnt:page

// Shared CTA button — drop child of any component via + * (<namespace>:ctaButton)
[<namespace>:ctaButton] > jnt:content, <namespace>Mix:component, <namespace>:linkTo
 - ctaLabel (string) i18n
```

### Step 7: Report

Tell the user:
```
Module created at: projects/<module-name>/
PROJECT_PATH = projects/<module-name>
```

Next: `/1-analyze <url>` or `/3-assets` if assets are already downloaded.
