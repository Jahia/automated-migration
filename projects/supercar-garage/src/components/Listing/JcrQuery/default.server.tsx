import {
  buildNodeUrl,
  Island,
  jahiaComponent,
  Render,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { useTranslation } from "react-i18next";
import type { JcrQueryProps } from "./types.js";
import { executeQuery, PAGE_SIZE } from "./utils.js";
import JcrQueryLoadMore from "./JcrQueryLoadMore.client.js";
import styles from "./jcrQuery.module.css";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:jcrQuery",
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
      "j:linknode": linknode,
      "j:url": url,
      loadMore,
      categoryFilter,
    }: JcrQueryProps,
    { currentNode, renderContext }: { currentNode: JCRNodeWrapper; renderContext: import("org.jahia.services.render").RenderContext },
  ) => {
    const { t } = useTranslation();
    const isEdit = renderContext.isEditMode();

    let linkUrl: string | undefined;
    if (linkType === "internal") {
      try {
        linkUrl = buildNodeUrl(linknode as JCRNodeWrapper);
      } catch (_) {}
    } else if (linkType === "external") {
      try {
        linkUrl = url;
      } catch (_) {}
    }

    const { nodes, queryId } = executeQuery({
      type,
      criteria,
      sortDirection,
      startNode,
      filter,
      excludeNodes,
      maxItems,
      loadMore,
      currentNode,
      renderContext,
    });

    const itemCount = nodes.length;

    return (
      <div className={styles.wrapper}>
        {isEdit && (
          <div className={styles.editInfo}>
            <strong>{type}</strong> | {itemCount} items | view:{" "}
            {subNodeView || "default"} | {criteria} {sortDirection}
          </div>
        )}

        {title && itemCount > 0 && (
          <div className={styles.headerRow}>
            <h2 className={styles.heading}>{title}</h2>
            {linkUrl && (
              <a href={linkUrl} className={styles.seeAll}>
                {t("common.seeAll")} →
              </a>
            )}
          </div>
        )}

        {itemCount > 0 ? (
          <div className={styles.grid} data-qgrid={queryId}>
            {nodes.map((node) => (
              <div
                key={node.getIdentifier()}
                data-qitem={queryId}
                data-lm-visible="true"
              >
                <Render node={node} view={subNodeView || "default"} readOnly />
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.empty}>
            {noResultText || t("jcrQuery.noResult")}
          </p>
        )}

        {loadMore && !isEdit && (
          <Island
            component={JcrQueryLoadMore}
            props={{ queryId, pageSize: PAGE_SIZE, total: itemCount }}
          />
        )}
      </div>
    );
  },
);
