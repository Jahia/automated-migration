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

## Load migration environment

```bash
ENV_FILE=$(find . -name "migration.env" | head -1)
if [ -z "$ENV_FILE" ]; then
  echo "ERROR: migration.env not found. Run /0-migration-start first."
  exit 1
fi
source "$ENV_FILE"
echo "Jahia: $JAHIA_URL | Site: $JAHIA_SITE_KEY | MCP: $MCP_AVAILABLE"
```

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

## CSS selectors (component-scoped)

Read `workflow-output/component-css-selectors.txt` — it contains CSS class names identified during asset import (skill 03) as belonging to individual components rather than global layout. When building this component's `.module.css`, pull rules matching these selectors from the imported CSS files in `static/css/`. Do not duplicate selectors already in Layout.tsx global imports.

If the file does not exist, extract CSS rules by grepping `static/css/` for the component's primary CSS class name (visible in the HTML fragment above).
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

**Quick path:** Check `workflow-output/component-css-selectors.txt` first — this pre-classified list from skill 03 maps component class names. Find your component's selectors there before grepping raw CSS.

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

   **Index the fallback array by position**, not a single constant — news cards, gallery items, and slides each need a distinct fallback to avoid all cards showing the same image:
   ```tsx
   const thumbnailUrl = thumbnailNode
     ? buildNodeUrl(thumbnailNode)
     : FALLBACK_IMAGES[idx % FALLBACK_IMAGES.length];
   ```

8b. **Date fields from JCR come as ISO strings (e.g. `2026-04-01T00:00:00.000Z`)** — always format them for the target locale before rendering. Use `toLocaleDateString()` with a try/catch for invalid values:
   ```tsx
   const rawDate = article.hasProperty("publishDate")
     ? article.getPropertyAsString("publishDate") : undefined;
   const publishDate = rawDate
     ? (() => {
         const d = new Date(rawDate);
         return isNaN(d.getTime()) ? rawDate
           : d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
       })()
     : undefined;
   ```
   Adjust the locale string (`"fr-FR"`, `"en-GB"`, etc.) to match the site's primary language.

9. **Icon-driven components need a CND `icon (string)` field** — if the source site uses icon fonts (Font Awesome, Material Icons) to differentiate component items, add `- icon (string)` to the child content type. The view reads this and falls back to a neutral default. Never hardcode icon classes — they are editorial choices:

10. **Font Awesome Pro icons in imported CSS/content must be replaced with FA Free equivalents** — Sitecore/SXA sites often use Font Awesome 6 Pro icons (e.g. `fa-bullseye-arrow`, `fa-lightbulb-gear`, `fa-circle-half-stroke`) which are not in the free CDN. In Layout.tsx, `@font-face` remaps "Font Awesome 6 Pro" to Free font files, but Pro-exclusive glyphs still render as empty boxes. Fix in two places:
    - **Layout.tsx**: the `@font-face` remapping to FA Free CDN handles most icons automatically
    - **JCR content**: when icon class strings are stored as content properties (e.g. `icon = "fa-solid fa-bullseye-arrow"`), fix them via GraphQL mutation after content creation. FA Free substitutes:

    | FA Pro (exclusive) | FA Free equivalent | Theme |
    |---|---|---|
    | `fa-bullseye-arrow` | `fa-solid fa-bullseye` | target / precision |
    | `fa-lightbulb-gear` | `fa-solid fa-gears` | innovation / settings |
    | `fa-circle-half-stroke` | `fa-solid fa-circle-half-stroke` | (exists in Free) |
    | `fa-sharp fa-*` | `fa-solid fa-*` equivalent | use solid variant |

    **Detection**: after content creation, check key-figure / stat components in the browser. An empty square where an icon should be = Pro-only glyph. Query JCR for the stored icon values and patch via GraphQL.
   ```cnd
   [ns:statItem] > jnt:content, jmix:hiddenType
     - icon (string)
     - value (string) i18n
   ```

11. **Never combine `container` and `col-*` on the same element.** Bootstrap's `col-12` sets `max-width: 100%` which overrides `container`'s `max-width: 1140px`. This is silent — no error, just a full-width layout. When a component needs a centered max-width wrapper, use one of two approaches:
    - `className="component-content container"` on a *child* div where no ancestor has `col-*` fighting it, OR
    - Inline style: `style={{ maxWidth: "1140px", margin: "0 auto", width: "100%" }}` — this always wins regardless of CSS cascade
    Prefer the inline style approach for component-content divs inside any section that has `col-12` on the outer wrapper.

12. **JS-dependent carousels render only the first item in SSR.** Libraries like Swiffy Slider set `overflow: hidden` on the container and rely on JS to translate slides. Without hydration, only slide 0 is visible. In server-only views (`.server.tsx` with no client island), always render carousels as a flex/grid layout so all items are visible without JS:
    ```tsx
    // Instead of Swiffy Slider markup:
    <ul style={{ display: "flex", flexWrap: "wrap", gap: "20px", listStyle: "none", padding: 0 }}>
      {items.map(item => <li key={item.getPath()}>...</li>)}
    </ul>
    // Add a client island only if animated sliding is required.
    ```

---

## After deploy: visual verification requires content

**Do NOT take a screenshot and declare "done" immediately after `yarn jahia-deploy`.** Components without JCR content look broken — collapsed carousels, missing icons, empty grids. This mimics CSS failures but is actually empty-content state.

**First: flush caches immediately after deploy**

```bash
curl -s -u "$JAHIA_USER:$JAHIA_PASS" \
  "$JAHIA_URL/cms/render/default/fr/sites/$JAHIA_SITE_KEY/home.flushCaches.do" \
  -o /dev/null -w "Cache flush: %{http_code}\n"
sleep 3
```

Do this BEFORE taking any screenshots. A stale cache produces a screenshot of the old broken render, not the new code.

**Correct gate after deploy:**

1. Run `yarn build && yarn jahia-deploy` — verify build succeeds and module is ACTIVE
2. Invoke skill 09 (create-content) for the home page components ONLY (not sub-pages)
3. Reload the page and take a screenshot of BOTH the reference home page and the Jahia home page
4. Compare them side by side — check: hero image present, section count matches, layout structure matches, fonts/colors match
5. Present side-by-side to user for VALIDATED gate

Only after VALIDATED proceed to sub-page content creation.

**What to look for in the comparison:**

| Check | Reference | Jahia | Pass? |
|---|---|---|---|
| Hero background image | Full-width photo | Photo OR blank | |
| Hero heading | Visible, correct font weight | Matches | |
| Section count (above fold) | N sections | N sections | |
| Grid layout | X columns | X columns | |
| CTA buttons | Color + border correct | Matches | |
| Font family | Matches CSS | Matches | |

If any row fails: fix the component before proceeding to sub-pages. A layout bug on the home page will appear on every page that uses the same component.

### fullPage view validation (for jmix:mainResource components)

After deploying any component with `needsFullPage: true`:
1. Create one test content node of that type in the JCR
2. Navigate directly to its URL: `$JAHIA_URL/cms/render/live/fr/sites/$JAHIA_SITE_KEY/contents/FOLDER/TEST-NODE.html`
3. Verify the page renders the full detail layout (not just the card)
4. Compare against the reference site's detail page for that content type

A `fullPage` view that is missing or broken will show a blank page when editors click through from listing cards — this is invisible until the content phase.

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
- [ ] No component uses JS-dependent carousel markup in a server-only view — use flex layout instead
- [ ] No `container` + `col-*` on the same element — pick one pattern per element

---

## Validation gate — one component at a time (MANDATORY)

A component is **not done until it passes its full probe**, and you do **not** start the
next component until it does. After adding/modifying any component (CND, view, resource
bundle, or content), run from the repo root:

```
orchestration/probes/component-validate.sh <project_path> <namespace> <ComponentDir> <smoke_page> <site_key> <lang>
# e.g. orchestration/probes/component-validate.sh projects/sial-paris sialp WhitePaper tendances/livres-blancs sial-paris fr
```

It runs the whole chain and exits non-zero on any failure: **source present → no duplicate
default-view (the crash that 404s the whole site) → CND patterns for that component → en+fr
resource keys for the type and every property → build → deploy → bundle ACTIVE → a non-home
page renders HTTP 200 → engine log free of `already exist`**.

- Always pass a real `smoke_page` that uses the component and the `site_key`. The render
  smoke on a **non-home** page is what catches a duplicate-view/registration crash (home
  alone keeps rendering and hides it).
- One default view per (nodeType): a second `jahiaComponent({componentType:'view', nodeType})`
  with no distinct `name:` throws `already exist` at module load and breaks every page using
  a not-yet-registered template. `grep -rn "nodeType: 'ns:foo'" src/` before adding a view.

---

## Content-type icons (jContent picker) — serving them in a JS module

The `@jahia/vite-plugin` does NOT process content-type icons, so they are NOT served
automatically. For a nodetype icon to show in jContent (Jahia resolves it to
`/modules/<module>/icons/<ns>_<type>.png`) you need BOTH:

1. The PNGs in a **root `icons/`** folder (32×32, named `<ns>_<type>.png`, e.g. `sialp_jcrQuery.png`).
2. `icons` added to **`files`** AND `/icons` added to **`jahia.static-resources`** in `package.json`:
   `"static-resources": "…,/static/assets,/images,/icons"`.

Without `/icons` in static-resources the URL 404s and jContent shows a fallback. Verify with
`curl /modules/<module>/icons/<ns>_<type>.png` → expect `200 image/png`.

Icons: generate from **Lucide** (`lucide-static` SVGs → `rsvg-convert -w 32 -h 32`), stroke
**black `#000000`** for contrast on jContent's white background (navy is too faint). Keep a copy in
`settings/content-types-icons/` too (the documented convention) and keep the two in sync.
