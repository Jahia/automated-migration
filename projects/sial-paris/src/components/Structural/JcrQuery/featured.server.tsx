import {
  buildNodeUrl,
  getNodesByJCRQuery,
  jahiaComponent,
  Render,
  server,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { RenderContext } from "org.jahia.services.render";
import { useTranslation } from "react-i18next";
import styles from "./jcrQueryFeatured.module.css";
import { buildQuery, getContentTypeLabel } from "./utils.js";
import type { JcrQueryProps } from "./types.js";

const MAX_ITEMS = 3;

/**
 * Featured layout view for sialp:jcrQuery.
 *
 * Two-column layout — up to 3 items:
 *   Left  (col 1): first item rendered with the "featured" view (full-height card)
 *   Right (col 2): items 2 and 3 stacked with the "compact" view
 *
 * Generic: works with any content type. Falls back to the content type's
 * default view when "featured" or "compact" views are not defined.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:jcrQuery",
    name: "featured",
    displayName: "Mise en avant (1 + 2)",
  },
  (
    {
      "jcr:title": title,
      "j:linkType": linkType,
      type,
      criteria,
      sortDirection,
      startNode,
      excludeNodes,
      filter,
      noResultText,
    }: JcrQueryProps,
    { currentNode, renderContext }: { currentNode: JCRNodeWrapper; renderContext: RenderContext },
  ) => {
    const { t } = useTranslation();
    const isEdit = renderContext.isEditMode();

    // Resolve contributor-selected "See all" link
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

    const allItems = getNodesByJCRQuery(currentNode.getSession(), jcrQuery, MAX_ITEMS);
    const items = allItems ?? [];
    const contentTypeLabel = getContentTypeLabel(type);
    const selectedCategoryFilters = (filter ?? [])
      .map((categoryNode) => categoryNode?.getDisplayableName() || categoryNode?.getName())
      .filter((name): name is string => Boolean(name));

    return (
      <div className={styles.wrapper}>

        {/* Edit mode info */}
        {isEdit && (
          <div className={styles.editInfo}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <strong>{contentTypeLabel}</strong>
            &nbsp;|&nbsp; {items.length}/{MAX_ITEMS} {t("jcrQuery.items")}
            &nbsp;|&nbsp; {t("jcrQuery.view")}: featured + compact
            &nbsp;|&nbsp; {criteria} {sortDirection}
            {selectedCategoryFilters.length > 0 && (
              <> &nbsp;|&nbsp; filtre configuré: {selectedCategoryFilters.join(", ")}</>
            )}
          </div>
        )}

        {isEdit && warn && (
          <div className={styles.warn} role="alert">{warn}</div>
        )}

        {/* Section heading + optional see-all link */}
        {(title || linkUrl) && items.length > 0 && (
          <div className={styles.headerRow}>
            {title && <h2 className={styles.heading}>{title}</h2>}
            {linkUrl && (
              <a href={linkUrl} className={styles.seeAll} aria-label={title}>
                {t("common.seeAll")} →
              </a>
            )}
          </div>
        )}

        {/* Layout */}
        {items.length > 0 ? (
          <div className={styles.layout}>

            {/* Left — first item, featured view */}
            <div className={styles.featuredSlot}>
              <Render node={items[0] as JCRNodeWrapper} view="featured" readOnly />
            </div>

            {/* Right — remaining items, compact view, stacked */}
            {items.length > 1 && (
              <div className={styles.sideSlots}>
                {items.slice(1).map((node) => (
                  <div key={node.getIdentifier()} className={styles.sideItem}>
                    <Render node={node as JCRNodeWrapper} view="compact" readOnly />
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <p className={styles.empty}>
            {noResultText || t("jcrQuery.noResult")}
          </p>
        )}
      </div>
    );
  },
);
