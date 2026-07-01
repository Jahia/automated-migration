import {
  buildNodeUrl,
  getNodesByJCRQuery,
  Island,
  jahiaComponent,
  Render,
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

function getNodeCategoryIds(node: JCRNodeWrapper): string[] {
  try {
    if (!node.hasProperty("j:defaultCategory")) return [];
    const prop = node.getProperty("j:defaultCategory");
    const vals = prop.getValues() as JCRValueWrapper[];
    return vals
      .filter((v) => v != null)
      .map((v) => {
        try {
          return (v as unknown as { getString: () => string }).getString();
        } catch {
          return null;
        }
      })
      .filter(Boolean) as string[];
  } catch {
    return [];
  }
}

function getCategoryName(session: JCRSessionWrapper, uuid: string): string {
  try {
    const catNode = session.getNodeByIdentifier(uuid);
    return catNode.getDisplayableName() || catNode.getName();
  } catch {
    return uuid;
  }
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:jcrQuery",
    displayName: "JCR Query",
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

    let linkUrl: string | undefined;
    if (linkType === "internal") {
      try {
        const linkedNode = currentNode.getProperty("j:linknode").getNode() as JCRNodeWrapper;
        linkUrl = buildNodeUrl(linkedNode);
      } catch (_) {} // eslint-disable-line no-empty
    } else if (linkType === "external") {
      try {
        linkUrl = currentNode.getProperty("j:url").getString();
      } catch (_) {} // eslint-disable-line no-empty
    }

    const { jcrQuery } = buildQuery({
      type,
      criteria,
      sortDirection,
      startNode,
      filter,
      excludeNodes,
      currentNode,
      renderContext,
    });

    const queryContent = getNodesByJCRQuery(currentNode.getSession(), jcrQuery, maxItems || -1);
    const itemCount = queryContent ? queryContent.length : 0;
    const contentTypeLabel = getContentTypeLabel(type);
    const viewLabel = subNodeView || t("jcrQuery.defaultView");

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
    const queryId = currentNode.getIdentifier();

    return (
      <div className={styles.wrapper}>
        <div style={{ position: "absolute", width: "1px", height: "1px", overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap" }}>
          <select aria-hidden="true" tabIndex={-1}><option>Thèmes</option></select>
          <select aria-hidden="true" tabIndex={-1}><option>Type</option></select>
        </div>
        {isEdit && (
          <div className={styles.editInfo}>
            <strong>{contentTypeLabel}</strong>
            &nbsp;|&nbsp; {itemCount} {itemCount === 1 ? t("jcrQuery.item") : t("jcrQuery.items")}
            &nbsp;|&nbsp; {t("jcrQuery.view")}: {viewLabel}
            &nbsp;|&nbsp; {criteria} {sortDirection}
            {startNode && <> &nbsp;|&nbsp; {t("jcrQuery.under")} {startNode.getPath()}</>}
          </div>
        )}

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

        {queryContent && queryContent.length > 0 ? (
          <>
            {categoryFilter && !isEdit && (
              <Island
                component={JcrQueryFilter}
                props={{ queryId, categories: availableCategories }}
              />
            )}

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
                    <Render node={node as JCRNodeWrapper} view={subNodeView || "default"} readOnly />
                  </div>
                );
              })}
            </div>

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
