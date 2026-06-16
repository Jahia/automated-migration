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

```cnd
// src/components/Content/JcrQuery/definition.cnd
// jmix:renderableList is NOT used — it injects j:linknode/j:url and limits view names.
[ns:jcrQuery] > jnt:content, mix:title, nsMix:pageComponent, jmix:list, jmix:cache
 - type (string, choicelist[resourceBundle]) indexed=no mandatory
   < 'ns:article', 'ns:event', 'ns:product'    // ← add all mainResource types in the module
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

Adapt the `< 'ns:article', ...` constraint to include all `jmix:mainResource` types in the module.

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
ns_jcrQuery.type.ui.tooltip=Which type of content to list.
ns_jcrQuery.type.ns:article=Articles
ns_jcrQuery.type.ns:event=Events
ns_jcrQuery.criteria=Sort by
ns_jcrQuery.criteria.ui.tooltip=Property used to order results.
ns_jcrQuery.criteria.jcr:created=Creation date
ns_jcrQuery.criteria.jcr:lastModified=Last modified date
ns_jcrQuery.criteria.j:lastPublished=Last published date
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

Every module that ships JCRQuery also ships GridRow:

```cnd
// src/components/Layout/GridRow/definition.cnd
[ns:gridRow] > jnt:content, nsMix:pageComponent
 - columns (string, choicelist[resourceBundle]) = '2' < '1', '2', '3', '4'
```

```tsx
// default.server.tsx
import { Area, jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import styles from "./gridRow.module.css";

jahiaComponent(
  { componentType: "view", nodeType: "ns:gridRow", displayName: "Grid Row" },
  ({ columns: rawCols }) => {
    const { renderContext, currentNode } = useServerContext();
    const cols = Math.min(4, Math.max(1, Number(rawCols) || 2));
    const isEdit = renderContext.isEditMode();
    const suffix = currentNode.getIdentifier().replace(/[^A-Za-z0-9]/g, "").slice(-8);
    const areaNames = Array.from({ length: cols }, (_, i) => `col${i + 1}_${suffix}`);

    return (
      <div className={styles.gridRow} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {areaNames.map((name) => (
          <div key={name} className={`${styles.column}${isEdit ? ` ${styles.columnEdit}` : ""}`}>
            <Area name={name} />
          </div>
        ))}
      </div>
    );
  }
);
```

---

## Validation checklist
- [ ] `type` choicelist constraint lists all `jmix:mainResource` types in the module
- [ ] `j:linkType (linkTypeInitializer)` present for the "see all" CTA
- [ ] No `jmix:renderableList` (it conflicts with custom view names)
- [ ] GridRow implemented alongside JCRQuery
- [ ] Resource bundle has all field labels + `ui.tooltip` for every field
- [ ] `yarn build && yarn jahia-deploy` — both types appear in Jahia content picker
