import {
  buildNodeUrl,
  getNodesByJCRQuery,
  Island,
  jahiaComponent,
  Render,
  server,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper, JCRSessionWrapper, JCRValueWrapper } from "org.jahia.services.content";
import type { RenderContext } from "org.jahia.services.render";
import { useTranslation } from "react-i18next";
import styles from "./jcrQuery.module.css";
import { buildQuery, getContentTypeLabel } from "./utils.js";
import type { JcrQueryProps } from "./types.js";
import JcrQueryFilter from "./JcrQueryFilter.client.jsx";
import JcrQueryLoadMore from "./JcrQueryLoadMore.client.jsx";
import type { CategoryMeta } from "./JcrQueryFilter.client.jsx";

const PAGE_SIZE = 6;

/** Extract j:defaultCategory UUIDs from a node (non-throwing) */
function getNodeCategoryIds(node: JCRNodeWrapper): string[] {
  try {
    if (!node.hasProperty("j:defaultCategory")) return [];
    const prop = node.getProperty("j:defaultCategory");
    const vals = prop.getValues() as JCRValueWrapper[];
    return vals
      .filter((v) => v != null)
      .map((v) => {
        try { return (v as unknown as { getString: () => string }).getString(); } catch { return null; }
      })
      .filter(Boolean) as string[];
  } catch {
    return [];
  }
}

/** Get display name for a category node by UUID (non-throwing) */
function getCategoryName(session: JCRSessionWrapper, uuid: string): string {
  try {
    const catNode = session.getNodeByIdentifier(uuid);
    return catNode.getDisplayableName() || catNode.getName();
  } catch {
    return uuid;
  }
}

/**
 * JcrQuery - auto-listing component for page Areas.
 *
 * Editors drop this into any page Area and configure:
 *   - jcr:title      : optional section heading (from mix:title)
 *   - type           : which node type to query (sialp:article | sialp:veilleLegale | ...)
 *   - criteria       : jcr:created | jcr:lastModified | j:lastPublished
 *   - sortDirection  : asc | desc
 *   - maxItems       : maximum items to display (no limit if unset)
 *   - startNode      : optional node to scope the query (page, folder...)
 *   - excludeNodes   : nodes to exclude from results
 *   - filter         : category-based filter (j:defaultCategory)
 *   - noResultText   : custom message when no results found
 *   - j:subNodesView : view name for each rendered card (default "default")
 *   - loadMore       : enable paginated load-more (PAGE_SIZE items at a time)
 *   - categoryFilter : enable category chip filter above the grid
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:jcrQuery",
    displayName: "Requete de contenu JCR",
  },
  (
    {
      "jcr:title": title,
      type,
      criteria,
      sortDirection,
      maxItems,
      startNode,
      excludeNodes,
      filter,
      noResultText,
      "j:subNodesView": subNodeView,
      "j:linkType": linkType,
      loadMore,
      categoryFilter,
    }: JcrQueryProps,
    { currentNode, renderContext }: { currentNode: JCRNodeWrapper; renderContext: RenderContext },
  ) => {
    const { t } = useTranslation();
    const isEdit = renderContext.isEditMode();
    const isInteractive = loadMore || categoryFilter;

    // Resolve the contributor-selected link (internal page or external URL)
    let linkUrl: string | undefined;
    if (linkType === "internal") {
      try {
        const linkedNode = currentNode.getProperty("j:linknode").getNode() as JCRNodeWrapper;
        linkUrl = buildNodeUrl(linkedNode);
      } catch (_) {}
    } else if (linkType === "external") {
      try {
        linkUrl = currentNode.getProperty("j:url").getString();
      } catch (_) {}
    }

    const { jcrQuery, warn } = buildQuery({
      shrQuery: {
        "jcr:title": title,
        type,
        criteria,
        sortDirection,
        startNode,
        filter,
        excludeNodes,
      },
      t,
      server,
      currentNode,
      renderContext,
    });

    // Always fetch all items - client handles load-more pagination
    const queryContent = getNodesByJCRQuery(currentNode.getSession(), jcrQuery, maxItems || -1);
    const itemCount = queryContent ? queryContent.length : 0;
    const contentTypeLabel = getContentTypeLabel(type);
    const viewLabel = subNodeView || t("jcrQuery.defaultView");
    const selectedCategoryFilters = (filter ?? [])
      .map((categoryNode) => categoryNode?.getDisplayableName() || categoryNode?.getName())
      .filter((name): name is string => Boolean(name));

    // ── Build per-item category metadata (only when categoryFilter is on) ──
    const session = currentNode.getSession() as JCRSessionWrapper;
    const categoryMap = new Map<string, CategoryMeta>();
    const itemCategoryIds: string[][] = [];

    if (isInteractive && queryContent) {
      queryContent.forEach((node) => {
        const ids = getNodeCategoryIds(node);
        itemCategoryIds.push(ids);
        if (categoryFilter) {
          ids.forEach((id) => {
            if (!categoryMap.has(id)) {
              categoryMap.set(id, { id, name: getCategoryName(session, id) });
            }
          });
        }
      });
    }

    const availableCategories: CategoryMeta[] = Array.from(categoryMap.values());

    // Unique ID to link island controls to their item grid in the DOM
    const queryId = currentNode.getIdentifier();

    return (
      <div className={styles.wrapper}>
        {/* ── Edit mode info panel ── */}
        {isEdit && (
          <div className={styles.editInfo}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <strong>{contentTypeLabel}</strong>
            &nbsp;|&nbsp; {itemCount} {itemCount === 1 ? t("jcrQuery.item") : t("jcrQuery.items")}
            &nbsp;|&nbsp; {t("jcrQuery.view")}: {viewLabel}
            &nbsp;|&nbsp; {criteria} {sortDirection}
            {startNode && <> &nbsp;|&nbsp; {t("jcrQuery.under")} {startNode.getPath()}</>}
            {loadMore && <> &nbsp;|&nbsp; load-more: {PAGE_SIZE}/{PAGE_SIZE}</>}
            {categoryFilter && <> &nbsp;|&nbsp; filtre categories: {availableCategories.length} cat.</>}
            {selectedCategoryFilters.length > 0 && (
              <> &nbsp;|&nbsp; filtre configuré: {selectedCategoryFilters.join(", ")}</>
            )}
          </div>
        )}

        {/* Warning for missing excluded nodes or categories */}
        {isEdit && warn && (
          <div className={styles.warn} role="alert">
            {warn}
          </div>
        )}

        {/* Optional section heading + optional "see all" link top right */}
        {title && queryContent && queryContent.length > 0 && (
          <div className={styles.headerRow}>
            <h2 className={styles.heading}>{title}</h2>
            {linkUrl && (
              <a href={linkUrl} className={styles.seeAll} aria-label={title}>
                {t("common.seeAll")} →
              </a>
            )}
          </div>
        )}

        {/* Results */}
        {queryContent && queryContent.length > 0 ? (
          <>
            {/* Category filter chips - above the grid */}
            {categoryFilter && !isEdit && (
              <Island
                component={JcrQueryFilter}
                props={{ queryId, categories: availableCategories }}
              />
            )}

            {/* Grid - each item carries data-* attributes for DOM-based filtering */}
            <div className={styles.grid} data-qgrid={queryId} data-subnodesview={subNodeView || "default"}>
              {queryContent.map((node, idx) => {
                const catIds = isInteractive ? (itemCategoryIds[idx] ?? []) : [];
                return (
                  <div
                    key={node.getIdentifier()}
                    data-qitem={queryId}
                    data-categories={catIds.join(",")}
                    data-cat-visible="true"
                    data-lm-visible="true"
                  >
                    <Render
                      node={node as JCRNodeWrapper}
                      view={subNodeView || "default"}
                      readOnly
                    />
                  </div>
                );
              })}
            </div>

            {/* Load-more button - below the grid */}
            {loadMore && !isEdit && (
              <Island
                component={JcrQueryLoadMore}
                props={{ queryId, pageSize: PAGE_SIZE, total: itemCount }}
              />
            )}
          </>
        ) : (
          <p className={styles.empty}>
            {noResultText || t("jcrQuery.noResult")}
          </p>
        )}
      </div>
    );
  },
);
