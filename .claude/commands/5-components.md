---
description: Implement all Jahia components via parallel subagents - CND, TSX, CSS, resource bundles. MANDATORY - the only correct way to implement components.
---

> See full skill guide at `.agents/skills/07-implement-components/SKILL.md`
> Agent rules at `.claude/agents/component-implementer.md`

# ⚠️ THIS IS THE ONLY CORRECT WAY TO IMPLEMENT COMPONENTS

Implement Jahia components using **parallel subagents** — one agent per component, all running simultaneously.

**NEVER manually create component files** - this command is MANDATORY, not optional.

**Terminology:** Use "implement" for component code generation, not "create".

## Input

The user will provide either:
- A component analysis document (from /analyze-website)
- Manual component specifications
- A list of component names and requirements

**Determine the project directory first** (contains `settings/definitions.cnd` or `package.json` with a `jahia` field):
1. Check if `settings/definitions.cnd` exists in current directory → `PROJECT_DIR="."`
2. Otherwise run `find . -name "definitions.cnd" -path "*/settings/*" | head -1` and use its grandparent dir
3. If ambiguous, ask the user which project to use

If `$PROJECT_DIR/workflow-output/component-manifest.json` exists, load it automatically.

---

## Orchestration Steps

### Step 1: Parse Component List

Collect the full list of components to implement. Each component needs:
- **Name** (PascalCase, e.g. `HeroSection`)
- **Node type** (e.g. `namespace:heroSection`)
- **Fields** — name, type, selector, keywords (i18n, multiple), default value, constraints
- **HTML fragment** — exact HTML structure with `{placeholders}` for dynamic content
- **Interactive** — true/false (whether it needs a client component)
- **Is container** — true/false (whether it holds child components)
- **Child type** — (if container) the node type of children

If the user provides a narrative description rather than a structured spec, extract these details from it.

### Step 2: Read Project Context

Read `settings/definitions.cnd` to discover:
- **Namespace prefix** (e.g. `carnivaldemo`, `bjhome`, `mysite`)
- **Mixin type name** (e.g. `carnivaldemo:componentMixin`)

If the file does not exist, ask the user for the namespace before proceeding.

Also read `package.json` to confirm the module name (`jahia.name` field).

### Step 3: Ensure Shared Mixin Exists

Check `settings/definitions.cnd` for a mixin that extends `jmix:droppableContent, jmix:accessControllableContent mixin`.

If it does **not** exist, add it to `settings/definitions.cnd` now (before spawning agents):

```cnd
[namespace:componentMixin] > jmix:droppableContent, jmix:accessControllableContent mixin
```

This step is done **by the orchestrator** (not by subagents) to avoid write conflicts.

**Also ensure the `linkTo` mixin and `ctaButton` are defined in `settings/definitions.cnd`:**

These shared types must exist before any component uses them. Add them now if absent:

```cnd
// Link mixin — extended by any component or type that needs a navigable link
// linkTypeInitializer is UI-only (shows/hides fields in editor). It does NOT inject
// j:url or j:linknode at runtime — they MUST be declared here explicitly.
[namespace:linkTo] mixin
 - ctaType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
 - j:url (string) indexed=no
 - j:linknode (weakreference) < jmix:mainResource, jnt:page

// CTA button type — accepts styled buttons as child nodes via + * (namespace:ctaButton)
[namespace:ctaButton] > jnt:content, namespace:componentMixin, namespace:linkTo
 - ctaLabel (string) i18n
```

**Critical:** `j:url` and `j:linknode` MUST be declared in the mixin. `linkTypeInitializer` only controls editor UI visibility — if you omit these properties from the CND, mutations will throw `ConstraintViolationException` at content-creation time.

**Why both are needed before agents run:**
- The `linkTo` mixin must exist before any component CND extends it
- The `ctaButton` type must exist before any `+ * (namespace:ctaButton)` child slot is declared
- Adding them here (orchestrator level) prevents race conditions between parallel agents

**Also create `jmix:mainResource` infrastructure if any component has `needsFullPage: true`:**

Check the manifest:
```bash
jq '[.components[] | select(.needsFullPage == true)] | length' workflow-output/component-manifest.json 2>/dev/null || echo "0"
```

If the count is > 0, create these **two shared files** (once per project — do NOT repeat per component type):

**`src/templates/MainResource/default.server.tsx`:**
```tsx
import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.jsx";

// Single base template for ALL jmix:mainResource types.
// Delegates to the "fullPage" view defined on each individual type.
jahiaComponent(
  { componentType: "template", nodeType: "jmix:mainResource", name: "default", displayName: "Main Resource Page" },
  (_, { currentNode }) => (
    <Layout title={(currentNode as JCRNodeWrapper).getDisplayableName() ?? ""}>
      <Render node={currentNode as JCRNodeWrapper} view="fullPage" />
    </Layout>
  )
);
```

**`src/templates/CMPreview.tsx`:**
```tsx
import { AddResources, buildModuleFileUrl } from "@jahia/javascript-modules-library";
import type { ReactNode } from "react";

// Lightweight wrapper for "cm" views (jContent editor preview panel).
// Loads module CSS without the full Layout chrome (no header/footer/nav).
export const CMPreview = ({ children }: { children: ReactNode }) => (
  <>
    <AddResources type="css" resources={buildModuleFileUrl("dist/assets/style.css")} />
    {/* Add project-specific static CSS here */}
    <main>{children}</main>
  </>
);
```

Skip if these files already exist.

**Also check if the module uses `useGQLQuery`** (GraphQL queries, not just `useJCRQuery`). If any component uses GraphQL queries, create the OSGi authorization config:

```bash
# Check if any component uses useGQLQuery
grep -r "useGQLQuery" "$PROJECT_DIR/src/" --include="*.tsx" | head -5
```

If matches are found, create `$PROJECT_DIR/settings/configurations/org.jahia.bundles.api.authorization-{module-name}.yml`:

```yaml
# Grants GraphQL API access from same-origin (hosted) requests
# Required for components using useGQLQuery with the live workspace
{module-name}:
  description: "Authorization to query live {ModuleName} content through the GraphQL API."
  auto_apply:
    - origin: hosted
  grants:
    - api:
        include: graphql
    - node:
        pathPattern: /,/files(/.*)?
```

Replace `{module-name}` with the value of `package.json`'s `jahia.name` field.

### Step 4: Launch One Agent Per Component (Parallel)

Use the **Agent tool** with `subagent_type: "general-purpose"` — one agent per component.

**IMPORTANT:** Custom agents defined in `.claude/agents/` are not available as subagent types in the Agent tool. Always use `general-purpose` and include this line at the top of every per-component agent prompt so the agent loads its rules:

```
First, read the file at .claude/agents/component-implementer.md for all implementation rules. Follow those rules exactly when writing component files.
```

**Launch ALL agents in a single message** (parallel tool calls) — do not wait for one to finish before starting the next.

Each agent receives a self-contained prompt with the component spec. The agent writes all files for that one component independently. All implementation rules are defined in `.claude/agents/component-implementer.md`.

#### Per-Component Agent Prompt Template

```
First, read the file at /path/to/project/.claude/agents/component-implementer.md for all implementation rules. Follow those rules exactly when writing component files.

**Critical rules (apply always — these are the most common agent failure modes):**
1. CND property order: `(type, selector) = 'default' keywords < constraints`
2. Use `component.css` (regular CSS), NOT `.module.css`
3. Always include `componentType: "view"` in jahiaComponent()
4. Containers: use `+ * (childType)` in CND, NEVER jmix:list
5. Never pass `props={props}` to Island — destructure into plain object
6. Never re-declare namespace in component definition.cnd
7. Render children with `<Render node={child} />` (no `view` prop)

## Working Directory
/path/to/project  ← (fill in the actual absolute path)

## Component to Implement

- Name: {ComponentName}
- Node type: {namespace:componentType}
- Display name: {Human Readable Name}
- Namespace mixin: {namespace:componentMixin}
- Interactive (needs client component): {true|false}
- Is container (holds child components): {true|false}
- Child node type (if container): {namespace:childType or none}
- Needs full page (jmix:mainResource): {true|false}
- Additional views: {[] or ["card","featured",...]}

## Fields

{For each field:}
- {fieldName} ({type}, {selector if any}) {= 'default' if any} {i18n if translatable} {multiple if array} {< constraints if any}

## HTML Fragment

Exact HTML structure this component must output (replace {placeholders} with prop values):

{paste exact HTML fragment here}

## Extra files required when needsFullPage is true

If `Needs full page: true`, create these files IN ADDITION to `default.server.tsx`:
1. `fullPage.server.tsx` — `name: "fullPage"`, `componentType: "view"` — full article/detail layout
2. `cm.server.tsx` — `name: "cm"`, `componentType: "view"` — jContent editor preview, wraps fullPage in CMPreview:
   ```tsx
   import { CMPreview } from "../../templates/CMPreview.jsx";
   jahiaComponent(
     { componentType: "view", nodeType: "ns:type", name: "cm", displayName: "..." },
     (_, { currentNode }) => <CMPreview><Render node={currentNode as JCRNodeWrapper} view="fullPage" /></CMPreview>
   );
   ```
Also add `jmix:mainResource` and `jmix:visibleInContentTree` to the CND supertypes.
The unified `src/templates/MainResource/default.server.tsx` is already created by the orchestrator — do NOT recreate it.
```

### Step 5: Wait for All Agents

All agents run in parallel. Once all complete, collect their results and summarize:
- Which components succeeded
- Which (if any) had issues

### Step 5.5: Deduplicate CND Definitions

After all agents finish, scan every `src/components/*/definition.cnd` for duplicate node type definitions.

**Why this happens:** A container agent (e.g. `ParentComponent`) often inlines child types (e.g. `namespace:childType`) in its own `definition.cnd`. A sibling agent implementing the child component independently also defines the same type in its own file. The result is the same `[namespace:type]` block appearing in two files.

**Detection — run this command:**
```bash
grep -rh '^\[' src/components/*/definition.cnd | sort | uniq -c | sort -rn
```

Any type appearing more than once is a duplicate.

**Resolution rule:** Keep the definition in the **child component's own dedicated file** (e.g. `ChildComponent/definition.cnd`). Remove it from any parent/container's `definition.cnd` (e.g. `ParentComponent/definition.cnd`).

**Steps:**
1. Read all `src/components/*/definition.cnd` files
2. Remove any namespace declarations (`<jnt = ...>`, `<jmix = ...>`, `<namespace = ...>`) from component `definition.cnd` files — these belong only in `settings/definitions.cnd`
3. For each type defined in more than one file:
   - Identify the "canonical" file (the component folder whose name matches the type)
   - Remove the duplicate block from all other files
4. Report which duplicates were removed and from which files

### Step 5.7: Verify Resource Bundle Coverage

After all agents complete, verify every new component has resource bundle entries:

```bash
# Find the module name
MODULE_NAME=$(jq -r '.jahia.name' $PROJECT_DIR/package.json)
BUNDLE_FILE="$PROJECT_DIR/settings/resources/$MODULE_NAME.properties"

# Check which component types have entries
echo "=== Resource bundle coverage ==="
for cnd_file in $PROJECT_DIR/src/components/*/definition.cnd; do
  component=$(dirname $cnd_file | xargs basename)
  # Extract the node type name from the CND
  node_type=$(grep -oP '(?<=\[)\S+(?=\])' $cnd_file | head -1)
  bundle_key=$(echo "$node_type" | tr ':' '_')
  
  if grep -q "^$bundle_key=" "$BUNDLE_FILE" 2>/dev/null; then
    echo "✅ $component ($node_type)"
  else
    echo "❌ MISSING: $component ($node_type) — needs $bundle_key= in $BUNDLE_FILE"
  fi
done
```

If any components are missing bundle entries, add them now before reporting success. A component without bundle entries will show raw technical names in the Jahia content editor.

**Minimum required keys per component:**
```properties
ns_componentType=Display Name
ns_componentType.propertyName=Property Label
```

**For choicelist properties:**
```properties
ns_componentType.propertyName.choiceValue=Display Label
```

### Step 5.8: Content Editor Form Overrides (When Needed)

Content editor form overrides in `settings/content-editor-forms/` customize the Jahia content editor UI. This is optional but needed when:
- A component has a "type" or "mode" selector that should dynamically show/hide other fields
- A component needs to auto-apply a mixin when a choicelist value is selected
- A component needs fields reordered or grouped differently from CND declaration order

**When to create an override:**
- Inspect the component spec for conditional fields (e.g., "show extra fields only when `type=advanced`")
- If a `choicelist` property controls which sub-type the node becomes, an override can auto-apply the corresponding mixin

**File structure:**
```
settings/content-editor-forms/
  fieldsets/
    {ns}_{typeName}.json    ← One file per content type needing override
  forms/
    {ns}_{typeName}.json    ← Full form override (less common)
```

**Example: Auto-apply a mixin when a "form type" choicelist is set**

`settings/content-editor-forms/fieldsets/namespace_contactForm.json`:
```json
{
  "name": "namespace:contactForm",
  "labelKey": "namespace_contactForm",
  "target": {
    "moduleId": "namespace",
    "displayOn": [{ "type": "create" }, { "type": "edit" }]
  },
  "sections": [
    {
      "name": "content",
      "fieldSets": [
        {
          "name": "namespace:contactForm",
          "fields": [
            {
              "name": "formType",
              "valueConstraints": [
                {
                  "value": "contact",
                  "displayValue": "Contact Form",
                  "propertyList": [{ "name": "addMixin", "value": "namespace:contactMixin" }]
                },
                {
                  "value": "newsletter",
                  "displayValue": "Newsletter Signup",
                  "propertyList": [{ "name": "addMixin", "value": "namespace:newsletterMixin" }]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

**Most components do NOT need form overrides.** Only create these when the analysis explicitly calls for conditional fields or mixin-switching behavior.

### Step 5.6: HTML Fidelity Spot-Check

For each implemented component, compare `default.server.tsx` against its HTML fragment from the manifest or analysis:

1. Count `data-*` attributes in the source HTML fragment
2. Count `data-*` attributes in the TSX JSX output
3. Verify any element IDs from the source are preserved (not renamed)
4. Verify `aria-*` and `role` attributes are present if they were in the source
5. If the source HTML has `<noscript>` fallbacks, verify they exist in the TSX

If any component has missing attributes, fix it before building.

### Step 6: Run Build

```bash
yarn build
```

If the build fails, read the TypeScript errors and fix them directly (do not re-spawn agents for minor fixes like import corrections). If a component has a fundamental structural error, note it in the report.

### Step 7: Save Implementation Report

Save `$PROJECT_DIR/workflow-output/implementation-report.json`:

```json
{
  "timestamp": "ISO date",
  "componentsRequested": 0,
  "componentsSucceeded": 0,
  "componentsFailed": 0,
  "buildStatus": "success | failed",
  "buildErrors": [],
  "components": [
    {
      "name": "ComponentName",
      "nodeType": "namespace:componentType",
      "status": "success | failed",
      "files": ["src/components/ComponentName/definition.cnd", "..."],
      "notes": ""
    }
  ]
}
```

### Step 8: Present Results

Show a summary table:

| Component | Status | Files | Notes |
|-----------|--------|-------|-------|
| HeroSection | ✅ success | 3 files | server-only |
| NavMenu | ✅ success | 4 files | client interactive |
| ContentGrid | ✅ success | 3 files | container |

Then give next steps:
```bash
yarn build   # if not already run
yarn deploy  # deploy to Jahia
```

Then use `/create-content` to add content to pages.

---

## ⚠️ Critical Rules Summary

### Rule 1: NEVER Use jmix:list

**User explicitly stated: "do not use jmix:list"**

When implementing container components (components that hold child components):

❌ **NEVER extend jmix:list**
```cnd
# WRONG - DO NOT DO THIS
[namespace:containerType] > jnt:content, namespace:mixin, jmix:list
```

✅ **ALWAYS use explicit child node definitions**
```cnd
# CORRECT - DO THIS
[namespace:containerType] > jnt:content, namespace:mixin
 - heading (string) i18n
 + * (namespace:childComponentType)  # Explicit child definition
```

**Why jmix:list fails:**
- Causes `javax.jcr.nodetype.ConstraintViolationException: No child node definition found`
- Requires explicit child definitions anyway

**Container detection patterns:**
- Component name contains: Grid, List, Carousel, Slider, Accordion, Tabs, Container, Section
- Analysis mentions: "contains", "holds", "collection", "repeated items"
- HTML shows repeated child elements

**If container → Add `+ * (childType)`, NEVER use jmix:list**

### Rule 2: Always Include componentType

All jahiaComponent() calls MUST include `componentType: "view"`.

### Rule 3: NEVER Pass `props={props}` Directly to Island

**The `props` argument in `jahiaComponent` is a JCR proxy object. Passing it directly to `Island` causes `Error: Invalid prop type` because the Island serializer cannot handle JCR proxy internals.**

```tsx
// ❌ WRONG - passes JCR proxy object → Invalid prop type at runtime
jahiaComponent(
  { nodeType: "namespace:type", displayName: "...", componentType: "view" },
  (props: Props) => <Island component={MyClient} props={props} />
);

// ✅ CORRECT - destructure and reconstruct a plain JS object
jahiaComponent(
  { nodeType: "namespace:type", displayName: "...", componentType: "view" },
  ({ title, body, imageUrl }: Props) => (
    <Island component={MyClient} props={{ title, body, imageUrl }} />
  )
);
```

### Rule 4: Navigation Components Must Be Dynamic (Use JCR APIs)

**NEVER hardcode navigation links in header/menu components.** Jahia provides JCR navigation APIs that build menus dynamically from the site's page tree.

#### The Pattern

Navigation components are **server-only** (no Island/client component needed) — they read the JCR tree at render time:

```tsx
import { buildNodeUrl, getChildNodes, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import "./component.css";

/** Get all direct child pages of a node */
const getChildPages = (node: JCRNodeWrapper) =>
  getChildNodes(node, -1, 0, (node) => node.isNodeType("jnt:page"));

jahiaComponent(
  { nodeType: "namespace:siteHeader", displayName: "Site Header", componentType: "view" },
  (_, { renderContext, mainNode }) => {
    const siteRoot = renderContext.getSite();
    const homePage = siteRoot.getNode("home");

    return (
      <header className="site-header">
        <nav className="site-header__nav">
          <ul className="menu">
            {getChildPages(homePage).map((page) => (
              <li key={page.getPath()} className="menu-item">
                <a
                  href={buildNodeUrl(page)}
                  aria-current={page.getPath() === mainNode.getPath() ? "page" : undefined}
                >
                  {page.getProperty("jcr:title").getString()}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
    );
  }
);
```

---

## What This Command Does

1. **Parses** the component list (from manifest or user input)
2. **Reads** project context (namespace, mixin) from settings/definitions.cnd
3. **Ensures** shared mixin exists (adds it if missing)
4. **Spawns** one parallel subagent per component (all at once)
5. **Waits** for all agents to finish
6. **Runs** `yarn build` to verify correctness
7. **Saves** implementation report to `$PROJECT_DIR/workflow-output/`

## After Implementation

After implementation is complete:
1. Run `yarn build` to compile components (already done in Step 6)
2. Run `yarn deploy` to deploy to Jahia
3. Verify component registration in Docker logs
4. Use `/create-content` to add content to pages
