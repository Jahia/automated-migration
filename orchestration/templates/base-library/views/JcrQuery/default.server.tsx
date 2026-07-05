import {
  buildNodeUrl,
  getNodesByJCRQuery,
  jahiaComponent,
  Render,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { RenderContext } from "org.jahia.services.render";
import { useTranslation } from "react-i18next";
import { resolveCtaUrl } from "../lib.js";
import { buildQuery } from "./utils.js";
import styles from "./jcrQuery.module.css";

/**
 * $NS:jcrQuery — the listing tool every module ships (CLAUDE.md rule 16). Editors
 * build listing pages without a developer: choose a content type, sort, cap, and
 * pick the card view. Generalized from lsp:jcrQuery — server-only core (no client
 * islands): query by type + ISDESCENDANTNODE scope, render each result via its
 * chosen view. Load-more / category-chip islands are a per-project add-on (P6.3).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:jcrQuery", displayName: "JCR Query" },
  (
    props: {
      "jcr:title"?: string;
      type?: string;
      criteria?: string;
      sortDirection?: string;
      maxItems?: number;
      startNode?: JCRNodeWrapper;
      filter?: JCRNodeWrapper[];
      noResultText?: string;
      "j:subNodesView"?: string;
      "j:linkType"?: string;
    },
    { currentNode, renderContext }: { currentNode: JCRNodeWrapper; renderContext: RenderContext },
  ) => {
    const { t } = useTranslation();
    const isEdit = renderContext.isEditMode();
    const title = props["jcr:title"];
    const subNodeView = props["j:subNodesView"] || "default";
    const linkUrl = resolveCtaUrl(props["j:linkType"], currentNode);

    const { jcrQuery } = buildQuery({
      type: props.type,
      criteria: props.criteria,
      sortDirection: props.sortDirection,
      startNode: props.startNode,
      filter: props.filter,
      currentNode,
      renderContext,
    });

    let results: JCRNodeWrapper[] = [];
    try {
      const found = getNodesByJCRQuery(currentNode.getSession(), jcrQuery, props.maxItems || -1);
      results = (found as JCRNodeWrapper[]) || [];
    } catch {
      results = [];
    }

    return (
      <div className={styles.wrapper}>
        {isEdit && (
          <div className={styles.editInfo}>
            <strong>{props.type || "—"}</strong>
            &nbsp;|&nbsp; {results.length}{" "}
            {results.length === 1 ? t("jcrQuery.item") : t("jcrQuery.items")}
            &nbsp;|&nbsp; {props.criteria || "jcr:created"} {props.sortDirection || "desc"}
          </div>
        )}

        {title && results.length > 0 && (
          <div className={styles.headerRow}>
            <h2 className={styles.heading}>{title}</h2>
            {linkUrl && (
              <a href={linkUrl} className={styles.seeAll} aria-label={title}>
                {t("common.seeAll")} &rarr;
              </a>
            )}
          </div>
        )}

        {results.length > 0 ? (
          <div className={styles.grid}>
            {results.map((node) => (
              <div key={node.getIdentifier()}>
                <Render node={node} view={subNodeView} readOnly />
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.empty}>{props.noResultText || t("jcrQuery.noResult")}</p>
        )}
      </div>
    );
  },
);
