---
name: 7-implement-components
description: Implement all Jahia components via parallel subagents. One agent per component, all running simultaneously. Use when implementing the full component set from an analysis manifest.
type: workflow
phase: 7
status: active
invokes_workflow: true
sub_skills:
  - support-create-view
  - support-deploy
depends_on:
  - 4-define-content-types
  - 5-implement-navigation
  - 6-implement-jcr-query
allowed-tools: Bash, Read, Write, Edit, Agent
---

# Skill: Implement Components

Implements ALL components at once using parallel subagents. Invoked by `/5-components`.

**This is the ONLY correct way to implement components.** Never write component files manually — the orchestration handles deduplication, resource bundle coverage, and build verification.

---

## Agent identity
- **Agent name:** Parallex
- **Reference style:** Factory / parallel assembly
- **Signature line (en):** *"N agents. N components. Zero waiting."*
- **Personality note:** Orchestrates, does not implement. Fans out one agent per component and synthesizes results. Stops the line if quality gates fail.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## Orchestration flow

```
1. Read component-manifest.json
2. Read settings/definitions.cnd → namespace prefix
3. Ensure shared mixin, linkTo, ctaButton exist
4. If any component needsFullPage: true → create MainResource template files
5. Launch ONE agent per component (all in parallel)
6. Wait for all agents
7. Deduplicate CND definitions
8. Verify resource bundle coverage
9. Run yarn build
10. Save implementation-report.json
```

---

## Step 3: Shared mixin guard

Before spawning agents, add to `settings/definitions.cnd` if missing:

```cnd
// Component mixin — extends jmix:droppableContent
[<ns>Mix:component] > jmix:droppableContent, jmix:accessControllableContent mixin
[<ns>Mix:pageComponent] > <ns>Mix:component mixin

// Link mixin — j:url and j:linknode MUST be declared here
[<ns>:linkTo] mixin
 - j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no
 - j:url (string) indexed=no
 - j:linknode (weakreference) < jmix:mainResource, jnt:page

// CTA button — used as child node via + * (<ns>:ctaButton)
[<ns>:ctaButton] > jnt:content, <ns>Mix:component, <ns>:linkTo
 - ctaLabel (string) i18n
```

---

## Step 4: MainResource infrastructure (if needed)

If any component has `needsFullPage: true`, create these once:

**`src/templates/MainResource/default.server.tsx`:**
```tsx
import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.jsx";

jahiaComponent(
  { componentType: "template", nodeType: "jmix:mainResource", name: "default", displayName: "Main Resource Page" },
  (_, { currentNode }) => (
    <Layout>
      <Render node={currentNode as JCRNodeWrapper} view="fullPage" />
    </Layout>
  )
);
```

---

## Step 5: Per-component agent prompt template

Each agent receives a self-contained prompt. Include `.claude/agents/component-implementer.md` path so the agent loads its rules:

```
First, read the file at <PROJECT_PATH>/.claude/agents/component-implementer.md for all implementation rules.

Working directory: <PROJECT_PATH>

## Component to Implement

- Name: {ComponentName}
- Node type: {ns:componentType}
- Namespace mixin: {nsMix:pageComponent}
- Interactive (client island needed): {true|false}
- Is container (holds child components): {true|false}
- Child node type: {ns:childType or none}
- Needs full page (jmix:mainResource): {true|false}

## Fields
{For each field: - fieldName (type, selector) = 'default' i18n|mandatory < constraints}

## HTML Fragment
{Exact HTML with {placeholders}}
```

---

## Step 7: Deduplication

After all agents complete:

```bash
grep -rh '^\[' src/components/*/definition.cnd | sort | uniq -c | sort -rn
```

Any type with count > 1 is a duplicate. Keep in the **child component's own folder**, remove from parent containers.

Also remove namespace declarations (`<jnt = ...>`, `<ns = ...>`) from component `definition.cnd` files — they belong only in `settings/definitions.cnd`.

---

## Step 8: Resource bundle coverage check

```bash
MODULE=$(jq -r '.jahia.name' package.json)
BUNDLE="settings/resources/$MODULE.properties"

for cnd in src/components/*/definition.cnd; do
  node_type=$(grep -oP '(?<=\[)\S+(?=\])' "$cnd" | head -1)
  key=$(echo "$node_type" | tr ':' '_')
  grep -q "^$key=" "$BUNDLE" && echo "ok: $node_type" || echo "MISSING: $node_type"
done
```

Add missing entries before reporting success.

---

### CSS class fidelity — inspect before implementing

The source CSS was designed for a specific HTML class structure. Components must output that EXACT class hierarchy or styling will not apply.

**Before implementing any component:**
1. Open the relevant source CSS file (grep for the component's section name)
2. Extract the exact CSS class selectors the CSS uses (`.component-name`, `.wrapper`, `.item`, etc.)
3. Map those to the TSX output — the JSX class names must match exactly

**For section background colors:**
- Check if the section uses a utility class for background color (e.g., `.bg-secondary-color`, `.bg-gray-1`, `.bg-dark`)
- Apply that class on the section wrapper in the TSX output
- Never hardcode background colors inline — the imported CSS owns the theming

**Common fidelity failure:** a component renders correctly in isolation but its section background, wave divider, or container width does not match because the outer wrapper is missing a class. Always wrap sections in the exact same outer element class as the source HTML.

---

### fullPage.server.tsx — critical constraints

- The `fullPage.server.tsx` view renders INSIDE `MainResource/default.server.tsx`, which itself wraps with `<Layout>`.
- **Never add `<Layout>`, `<header>`, `<footer>`, `<nav>`, or `<AbsoluteArea>` inside a `fullPage.server.tsx`.**
- The fullPage view renders ONLY the article-level content body (title, image, body text, tags, date, related items).
- Similarly, `MainResource/default.server.tsx` should use `<Layout>` ONCE and delegate to `<Render ... view="fullPage" />`. Never render AbsoluteArea header/footer separately inside mainResource.

---

## Critical rules (apply to every component agent)

1. **NEVER use `jmix:list`** — use `+ * (childType)` for containers
2. **Always include `componentType: "view"`** in jahiaComponent()
3. **Never pass `props={props}` to Island** — destructure into a plain JS object
4. **Never hardcode nav links** — use `getChildNodes` + `buildNodeUrl`
5. **CND property order:** `(type, selector) = 'default' keywords < constraints`
6. **Use `component.module.css`** (CSS Module), not plain `.css` for component styles
7. **All props optional in `types.ts`** — even mandatory CND fields
8. **Every image-rendering component needs a static fallback** — if a component reads a `weakreference` image and no JCR content exists, it collapses to 0px height. This looks like a CSS failure. Always declare `FALLBACK_IMAGES` at the top of the view and use them when the JCR property is absent:
   ```tsx
   const FALLBACK_IMAGES = [
     "static/assets/images/slide-1.jpg",
     "static/assets/images/slide-2.jpg",
   ];
   // use: buildModuleFileUrl(FALLBACK_IMAGES[idx % FALLBACK_IMAGES.length])
   // when slide.hasProperty("backgroundImage") is false or the node cannot be resolved
   ```
   Fallback images must have been downloaded in skill 03 (import-assets).

9. **Icon-driven components need a CND `icon (string)` field** — if the source site uses icon fonts (Font Awesome, Material Icons) to differentiate component items, add `- icon (string)` to the child content type. The view reads this and falls back to a neutral default. Never hardcode icon classes — they are editorial choices:
   ```cnd
   [ns:statItem] > jnt:content, jmix:hiddenType
     - icon (string)
     - value (string) i18n
   ```

---

## After deploy: visual verification requires content

**Do NOT take a screenshot and declare "done" immediately after `yarn jahia-deploy`.** Components without JCR content look broken — collapsed carousels, missing icons, empty grids. This mimics CSS failures but is actually empty-content state.

**Correct gate after deploy:**

1. Run `yarn build && yarn jahia-deploy` — verify build succeeds and module is ACTIVE
2. Invoke skill 09 (create-content) for the home page components ONLY (not sub-pages)
3. Reload the page and take a screenshot
4. Present to user for VALIDATED gate

Only after VALIDATED proceed to sub-page content creation.

---

## Validation checklist
- [ ] All agents completed (no crashes)
- [ ] CND deduplication run — no type defined in 2+ files
- [ ] Resource bundle coverage 100% — every type has at least a label key
- [ ] Every label key has a companion `ui.tooltip` key
- [ ] `yarn build` succeeds with no TypeScript errors
- [ ] Components with `needsFullPage: true` have `default.server.tsx` AND `fullPage.server.tsx`
- [ ] JCRQuery and GridRow components present in the module
- [ ] Navigation component uses JCR tree (no hardcoded links)
- [ ] Every image-rendering component has a `FALLBACK_IMAGES` constant and uses it
- [ ] Every icon-driven child type has an `icon (string)` CND field
