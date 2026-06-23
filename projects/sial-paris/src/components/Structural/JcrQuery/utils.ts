import type { JcrQueryProps } from "./types";
import type { RenderContext } from "org.jahia.services.render";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { TFunction } from "i18next";
import { server } from "@jahia/javascript-modules-library";

interface BuildQueryProps {
  shrQuery: JcrQueryProps;
  t: TFunction;
  server: typeof server;
  currentNode: JCRNodeWrapper;
  renderContext: RenderContext;
}

export const buildQuery = ({
  shrQuery,
  t,
  server,
  currentNode,
  renderContext,
}: BuildQueryProps) => {
  let warn: string | null = null;
  const asContent = "content";

  const descendantPath =
    shrQuery.startNode?.getPath() || `${currentNode.getResolveSite().getPath()}`;

  /**
   * Build filter based on category
   */
  const filter =
    shrQuery.filter?.reduce((condition, categoryNode, index) => {
      if (!categoryNode) {
        warn = t("query.catIsMissing", { queryName: shrQuery["jcr:title"] });
        return condition;
      }
      return `${condition} ${index === 0 ? "" : "OR"} ${asContent}.[j:defaultCategory] = '${categoryNode.getIdentifier()}'`;
    }, "") || "";
  const queryFilter = filter.trim().length > 0 ? `AND (${filter})` : "";

  /**
   * Build filter based on excludeNodes
   */
  const excludeNodes =
    shrQuery.excludeNodes?.reduce((condition, excludeNode, index) => {
      if (!excludeNode) {
        warn = t("query.excludeIsMissing", { queryName: shrQuery["jcr:title"] });
        return condition;
      }
      const translationNode = excludeNode.getNode(
        `j:translation_${renderContext.getMainResourceLocale().getLanguage()}`,
      );
      const extraLanguageNode = translationNode
        ? `AND ${asContent}.[jcr:uuid] <> '${translationNode.getIdentifier()}'`
        : "";
      return `${condition} ${index === 0 ? "" : "OR"} (${asContent}.[jcr:uuid] <> '${excludeNode.getIdentifier()}' ${extraLanguageNode})`;
    }, "") || "";
  const queryExcludeNodes = excludeNodes.trim().length > 0 ? `AND (${excludeNodes})` : "";

  const jcrQuery = `SELECT *
                    FROM [${shrQuery.type}] AS ${asContent}
                    WHERE ISDESCENDANTNODE('${descendantPath}') ${queryFilter} ${queryExcludeNodes}
                    ORDER BY ${asContent}.[${shrQuery.criteria}] ${shrQuery.sortDirection}`;

  server.render.addCacheDependency(
    { flushOnPathMatchingRegexp: `${descendantPath}/.*` },
    renderContext,
  );

  return { jcrQuery, warn };
};

const CONTENT_TYPE_LABELS: Record<string, string> = {
  "jmix:mainResource": "Contenu (main resource)",
  "jmix:editorialContent": "Contenu éditorial",
  "sialp:newsArticle": "Actualités",
  "sialp:focusArticle": "Focus Tendances",
};

export const getContentTypeLabel = (type: string): string =>
  CONTENT_TYPE_LABELS[type] || type;
