---
name: 6-implement-jcr-query
description: Implement the JCRQuery listing component and GridRow layout component. Mandatory for every migration. Supports type selector, sort, filter, load-more, category chips.
type: production
phase: 6
status: active
depends_on:
  - 4-define-content-types
allowed-tools: Bash, Read, Write, Edit
---

# Skill: Implement JCRQuery

The JCRQuery component is a **required deliverable in every migration**. Editors use it to build listing pages without developer help: choose content type, sort order, scope, and view — results appear automatically.

---

## Agent identity
- **Agent name:** Queryon
- **Reference style:** Library / information retrieval
- **Signature line (en):** *"Ask the repository. It always answers."*
- **Personality note:** Knows the difference between jmix:list and jmix:renderableList. Uses jmix:cache. Always adds the GridRow companion.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## CND definition

First declare a **marker mixin** in `settings/definitions.cnd` — content types opt in to the
query dropdown by extending it. This keeps the `type` dropdown short (only the few listable
types) instead of every node type in the module:

```cnd
// settings/definitions.cnd
// Marker mixin: add to any content type that should be selectable in a JcrQuery `type` dropdown.
[nsMix:queryContent] mixin
```

```cnd
// A listable content type opts in by extending nsMix:queryContent:
[ns:article] > jnt:content, mix:title, jmix:mainResource, nsMix:queryContent, jmix:tagged, jmix:categorized
 - ...
```

```cnd
// src/components/Content/JcrQuery/definition.cnd
// jmix:renderableList is NOT used — it injects j:linknode/j:url and limits view names.
[ns:jcrQuery] > jnt:content, mix:title, nsMix:pageComponent, jmix:list, jmix:cache
 - type (string, choicelist[subnodetypes = 'jnt:page, nsMix:queryContent', resourceBundle]) indexed=no mandatory
   // ↑ `subnodetypes` auto-populates the dropdown with every type extending nsMix:queryContent
   //   (+ jnt:page). NEVER hardcode a '< type, type, ...' list and NEVER list generic jmix
   //   mixins — opt types in via the marker mixin so the dropdown stays short and curated.
 - criteria (string, choicelist[resourceBundle]) = 'jcr:created' autocreated indexed=no
   < 'jcr:created', 'jcr:lastModified', 'j:lastPublished'
 - sortDirection (string, choicelist[resourceBundle]) = 'desc' autocreated indexed=no
   < 'asc', 'desc'
 - maxItems (long) indexed=no
 - startNode (weakreference) indexed=no
 - excludeNodes (weakreference) multiple indexed=no
 - filter (weakreference, category[autoSelectParent=false]) multiple indexed=no
 - noResultText (string) i18n indexed=no
 - j:subNodesView (string, choicelist[templates=subnodes,resourceBundle,image,dependentProperties='type']) nofulltext indexed=no
 - j:linkType (string, choicelist[linkTypeInitializer]) indexed=no
 - loadMore (boolean) = false indexed=no
 - categoryFilter (boolean) = false indexed=no
```

The `type` dropdown is driven by the `nsMix:queryContent` **marker mixin** + the
`subnodetypes` initializer — so it lists exactly the types that opted in (e.g.
`ns:newsArticle`, `ns:focusArticle`), never a hardcoded list and never the full component
catalogue. Scope a query to a content folder with `startNode` (e.g. `contents/news`,
`contents/focus`). Do **not** ship a minimalist hardcoded-`nodeType`/`basePath` variant —
use this full component with `criteria`, `sortDirection`, `filter`, `loadMore`,
`categoryFilter`, `j:subNodesView` and the edit-mode info panel. Each result is rendered
with the content type's own card view via `<Render view={subNodesView} />`; the listing
carries no per-type markup. `buildQuery` uses the stored `type` value directly in
`SELECT * FROM [<type>]`, so it works whether the editor picked a concrete type or `jnt:page`.

---

## View structure

The view has 3 parts:
1. `default.server.tsx` — main server component
2. `JcrQueryFilter.client.tsx` — category chip filter (Island)
3. `JcrQueryLoadMore.client.tsx` — load-more pagination button (Island)

### Query builder utility

```tsx
// utils.ts
import type { JCRSessionWrapper } from "org.jahia.services.content";
import type { RenderContext } from "org.jahia.services.render";

export function buildQuery({
  type, criteria, sortDirection, startNode, filter, excludeNodes, currentNode, renderContext
}: {
  type?: string; criteria?: string; sortDirection?: string;
  startNode?: any; filter?: any[]; excludeNodes?: any[];
  currentNode: any; renderContext: RenderContext;
}): { jcrQuery: string; warn?: string } {
  const scopePath = startNode
    ? startNode.getPath()
    : renderContext.getSite().getPath() + "/contents";

  const orderBy = criteria || "jcr:created";
  const direction = sortDirection === "asc" ? "asc" : "desc";

  let jcrQuery = `SELECT * FROM [${type}] AS n WHERE ISDESCENDANTNODE(n, '${scopePath}') ORDER BY n.[${orderBy}] ${direction}`;

  if (filter && filter.length > 0) {
    const catIds = filter
      .filter((n) => n != null)
      .map((n) => `'${n.getIdentifier()}'`).join(", ");
    if (catIds) jcrQuery = jcrQuery.replace(" ORDER BY", ` AND n.[j:defaultCategory] IN (${catIds}) ORDER BY`);
  }

  return { jcrQuery };
}
```

### Server component skeleton

```tsx
import {
  buildNodeUrl, getNodesByJCRQuery, Island,
  jahiaComponent, Render, server,
} from "@jahia/javascript-modules-library";
import { useTranslation } from "react-i18next";
import { buildQuery } from "./utils.js";
import styles from "./jcrQuery.module.css";

const PAGE_SIZE = 6;

jahiaComponent(
  { componentType: "view", nodeType: "ns:jcrQuery", displayName: "JCR Query" },
  ({
    "jcr:title": title, type, criteria, sortDirection, maxItems,
    startNode, excludeNodes, filter, noResultText,
    "j:subNodesView": subNodeView, "j:linkType": linkType,
    loadMore, categoryFilter,
  }, { currentNode, renderContext }) => {
    const { t } = useTranslation();
    const isEdit = renderContext.isEditMode();

    // Resolve "see all" link
    let linkUrl: string | undefined;
    if (linkType === "internal") {
      try { linkUrl = buildNodeUrl(currentNode.getProperty("j:linknode").getNode()); } catch (_) {}
    } else if (linkType === "external") {
      try { linkUrl = currentNode.getProperty("j:url").getString(); } catch (_) {}
    }

    const { jcrQuery } = buildQuery({ type, criteria, sortDirection, startNode, filter, excludeNodes, currentNode, renderContext });
    const queryContent = getNodesByJCRQuery(currentNode.getSession(), jcrQuery, maxItems || -1);
    const itemCount = queryContent?.length ?? 0;
    const queryId = currentNode.getIdentifier();

    return (
      <div className={styles.wrapper}>
        {isEdit && (
          <div className={styles.editInfo}>
            <strong>{type}</strong> | {itemCount} items | view: {subNodeView || "default"} | {criteria} {sortDirection}
          </div>
        )}

        {title && itemCount > 0 && (
          <div className={styles.headerRow}>
            <h2 className={styles.heading}>{title}</h2>
            {linkUrl && <a href={linkUrl} className={styles.seeAll}>{t("common.seeAll")} →</a>}
          </div>
        )}

        {queryContent && itemCount > 0 ? (
          <div className={styles.grid} data-qgrid={queryId}>
            {queryContent.map((node, idx) => (
              <div key={node.getIdentifier()} data-qitem={queryId}
                   data-lm-visible="true">
                <Render node={node} view={subNodeView || "default"} readOnly />
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.empty}>{noResultText || t("jcrQuery.noResult")}</p>
        )}

        {loadMore && !isEdit && (
          <Island component={JcrQueryLoadMore}
                  props={{ queryId, pageSize: PAGE_SIZE, total: itemCount }} />
        )}
      </div>
    );
  }
);
```

---

## Resource bundle entries

```properties
ns_jcrQuery=JCR Query
ns_jcrQuery.ui.tooltip=Listing component. Automatically queries and renders content by type.
ns_jcrQuery.type=Content type
ns_jcrQuery.type.ui.tooltip=Which content to list (only types that opt in via nsMix:queryContent appear here).
# NOTE: the ':' in a key MUST be escaped as '\:' in .properties, or Java parses it as the
#       key/value separator and the label breaks. This applies to every value with a prefix.
# One label per type that extends nsMix:queryContent (the subnodetypes dropdown relabels via these):
ns_jcrQuery.type.ns\:article=Articles
ns_jcrQuery.type.ns\:event=Events
ns_jcrQuery.type.jnt\:page=Pages
ns_jcrQuery.criteria=Sort by
ns_jcrQuery.criteria.ui.tooltip=Property used to order results.
ns_jcrQuery.criteria.jcr\:created=Creation date
ns_jcrQuery.criteria.jcr\:lastModified=Last modified date
ns_jcrQuery.criteria.j\:lastPublished=Last published date
ns_jcrQuery.sortDirection=Sort order
ns_jcrQuery.sortDirection.ui.tooltip=Ascending (oldest first) or descending (newest first).
ns_jcrQuery.sortDirection.asc=Ascending
ns_jcrQuery.sortDirection.desc=Descending
ns_jcrQuery.maxItems=Maximum items
ns_jcrQuery.maxItems.ui.tooltip=Leave empty to show all results.
ns_jcrQuery.startNode=Scope
ns_jcrQuery.startNode.ui.tooltip=Optional: limit results to descendants of this node.
ns_jcrQuery.filter=Category filter
ns_jcrQuery.filter.ui.tooltip=Optional: only show items tagged with these categories.
ns_jcrQuery.noResultText=No results message
ns_jcrQuery.noResultText.ui.tooltip=Text shown when no items match the query.
ns_jcrQuery.j:linkType=See all link
ns_jcrQuery.j:linkType.ui.tooltip=Optional link shown at the top-right of the listing (e.g. "See all articles").
ns_jcrQuery.loadMore=Enable load-more
ns_jcrQuery.loadMore.ui.tooltip=Show a "Load more" button instead of rendering all results at once.
ns_jcrQuery.categoryFilter=Category chips
ns_jcrQuery.categoryFilter.ui.tooltip=Show category filter chips above the listing.
```

---

## GridRow companion component

Every module that ships JCRQuery also ships GridRow. Canonical implementation (from `soprahr/mysoprahr`):

```cnd
// src/components/GridRow/definition.cnd
[ns:gridRow] > jnt:content, nsMix:pageComponent
 - columns (string, choicelist[resourceBundle]) = '2' < '1', '2', '3', '4'
 + * (jmix:droppableContent) = jmix:droppableContent
```

```tsx
// src/components/GridRow/default.server.tsx
import { AbsoluteArea, jahiaComponent } from "@jahia/javascript-modules-library";
import styles from "./gridRow.module.css";

const MAX_COLS = 4;
const MIN_COLS = 1;
const DEFAULT_COLS = 2;

function parseColumns(raw: unknown): number {
  const n = Number(raw);
  if (Number.isNaN(n) || n < MIN_COLS) return DEFAULT_COLS;
  return Math.min(MAX_COLS, Math.trunc(n));
}

jahiaComponent(
  { componentType: "view", nodeType: "ns:gridRow", displayName: "Grid Row" },
  ({ columns: rawCols }: { columns?: string }, { currentNode }) => {
    const cols = parseColumns(rawCols);
    const areaNames = Array.from({ length: cols }, (_, index) => index);

    return (
      <section className={styles.root}>
        <div
          className={styles.row}
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        >
          {areaNames.map((col) => (
            <div key={col} className={styles.col}>
              <AbsoluteArea parent={currentNode} name={`${currentNode.getName()}-col-${col}`} />
            </div>
          ))}
        </div>
      </section>
    );
  },
);
```

```css
/* src/components/GridRow/gridRow.module.css */
.root {
  width: 100%;
}

.row {
  display: grid;
  width: 100%;
  gap: 1.5rem;
  align-items: stretch;
}

.col {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.col > * {
  min-width: 0;
}

@media (max-width: 1024px) {
  .row { gap: 1.25rem; }
}

@media (max-width: 767px) {
  .row {
    grid-template-columns: 1fr !important;
    gap: 1rem;
  }
}
```

**Key design decisions:**
- Uses `AbsoluteArea` (not `Area`) — each column is a named absolute area keyed by `${currentNode.getName()}-col-${index}`, making it stable and unique across the page tree.
- `parseColumns()` is a dedicated guard function — clamps to [1–4], defaults to 2 on invalid input, uses `Math.trunc` to reject decimals.
- CSS grid with `minmax(0, 1fr)` — prevents overflow on narrow content. The `min-width: 0` on `.col` enforces the same at the flex child level.
- Mobile breakpoint at 767px forces single-column via `!important` to override the inline `gridTemplateColumns` style.
- No edit-mode branch — `AbsoluteArea` handles editor chrome automatically.

---

## Validation checklist
- [ ] `nsMix:queryContent` marker mixin declared in `settings/definitions.cnd`
- [ ] Every listable content type extends `nsMix:queryContent` (so it appears in the dropdown); non-listable components do NOT
- [ ] `type` uses `choicelist[subnodetypes = 'jnt:page, nsMix:queryContent', resourceBundle]` — NOT a hardcoded `< ... >` list and NOT generic `jmix:*` mixins
- [ ] All choicelist values with a prefix (`ns:`, `jcr:`, `j:`, `jnt:`) are escaped as `\:` in the `.properties` keys
- [ ] Full field set present: `criteria`, `sortDirection`, `maxItems`, `startNode`, `excludeNodes`, `filter`, `noResultText`, `j:subNodesView`, `j:linkType`, `loadMore`, `categoryFilter` — NOT a minimalist `nodeType`/`basePath` variant
- [ ] Results rendered via `<Render view={subNodesView} />` (each type's own card view) — no per-type markup in the query
- [ ] Match the reference card LAYOUT and COLUMN COUNT per content type. A type may ship several card views (e.g. a vertical grid card vs a horizontal image-left/text-right card), picked per listing with `j:subNodesView`. The grid div carries `data-subnodesview`, so CSS adapts columns per view — e.g. `.grid[data-subnodesview="card"] { grid-template-columns: repeat(2, 1fr) }` for horizontal focus cards (2 per row), with a `@media (max-width:767px)` override back to `1fr`. The attribute selector outranks the generic `.grid` mobile rule, so the mobile override MUST repeat the `[data-subnodesview="card"]` selector. Measure width/orientation/per-row with `getBoundingClientRect` against the reference — don't assume.
- [ ] Content WIDTH is a template-level concern, not per-component. This template set's `<main>` is full-width (heroes/banners/carousels go full-bleed); content is centered by a global `main .component:not(...) { max-width: 1340px; margin: 0 auto }` rule in `Layout.tsx`. Set the listing column width there to match the reference — the JcrQuery `.wrapper` just mirrors that max-width. Card pixel width then follows from `(column − padding − gaps) / columns` (e.g. 1340 − 32 − 20 ÷ 2 ≈ 644px).
- [ ] Filter chips + load-more are client islands coordinated via `data-qitem`/`data-cat-visible`/`data-lm-visible`
- [ ] Edit-mode info panel shows type / count / view / sort / scope
- [ ] `j:linkType (linkTypeInitializer)` present for the "see all" CTA
- [ ] No `jmix:renderableList` (it conflicts with custom view names)
- [ ] GridRow implemented alongside JCRQuery
- [ ] Wrapper width matches the template set: if `main`/the page container is **full-width**, the listing `.wrapper` must self-constrain (`max-width: <site content width>; margin: 0 auto; padding: 2rem 1rem; box-sizing: border-box`) so results aren't edge-to-edge; if the page template already provides a centered container, leave `.wrapper { width: 100% }`. Verify with `getBoundingClientRect` (centered = equal left/right gap), never by eyeballing.
- [ ] Reference implementation: soprahr `mysoprahr/src/components/JcrQuery` (canonical); sial-paris `Structural/JcrQuery` (replicated)
- [ ] Resource bundle has all field labels + `ui.tooltip` for every field
- [ ] `yarn build && yarn jahia-deploy` — both types appear in Jahia content picker

## News / articles / press = `jmix:mainResource` structured content, NOT sub-pages

A recurring migration mistake: modelling news/articles/events as child **pages** (empty `jnt:page` shells) and relying on an SXA-style facet/search widget to "list" them. In Jahia that's wrong:
- Anything that needs a **listing card AND its own full-page URL** must be a `jmix:mainResource` content type (e.g. `ns:newsArticle > jnt:content, mix:title, jmix:mainResource, jmix:tagged`), created in a `jnt:contentFolder` (e.g. `/sites/<site>/contents/actualites`), and rendered full-page by the MainResource template.
- List them with a `ns:jcrQuery` (`type`, `startNode`, `criteria`, `sortDirection`, `j:subNodesView`) whose card view is the content type's `default` view. The query is `select * from [type] where isdescendantnode(startNode)`.
- An imported **SXA `facetFilter`** (dropdowns hitting `/sxa/search/...`) is a search UI with **no backend in Jahia** — it renders empty controls and never lists content. Don't treat it as a listing; pair the page with a real `jcrQuery` (the facet bar can stay as decoration or be removed).
- Make the `jcrQuery` `type` picker usable by editors: `choicelist[subnodetypes='jmix:mainResource']` — NOT `subnodetypes='jnt:page'`, or editors can't select content types and the listing can only be wired by a developer via raw mutations.
Symptom this prevents: "I have no news — structured content / jmix:mainResource ???"
