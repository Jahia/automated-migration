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

## Critical rules (apply to every component agent)

1. **NEVER use `jmix:list`** — use `+ * (childType)` for containers
2. **Always include `componentType: "view"`** in jahiaComponent()
3. **Never pass `props={props}` to Island** — destructure into a plain JS object
4. **Never hardcode nav links** — use `getChildNodes` + `buildNodeUrl`
5. **CND property order:** `(type, selector) = 'default' keywords < constraints`
6. **Use `component.module.css`** (CSS Module), not plain `.css` for component styles
7. **All props optional in `types.ts`** — even mandatory CND fields

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
