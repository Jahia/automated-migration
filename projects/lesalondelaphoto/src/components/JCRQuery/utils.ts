import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { RenderContext } from "org.jahia.services.render";
import type { JcrQueryProps } from "./types.js";

interface BuildQueryInput {
  type?: string;
  criteria?: string;
  sortDirection?: string;
  startNode?: JCRNodeWrapper;
  filter?: JCRNodeWrapper[];
  excludeNodes?: JCRNodeWrapper[];
  currentNode: JCRNodeWrapper;
  renderContext: RenderContext;
}

export function buildQuery({
  type,
  criteria,
  sortDirection,
  startNode,
  filter,
  excludeNodes,
  currentNode,
  renderContext,
}: BuildQueryInput): { jcrQuery: string; warn?: string } {
  const scopePath = startNode
    ? startNode.getPath()
    : renderContext.getSite().getPath() + "/contents";

  const orderBy = criteria || "jcr:created";
  const direction = sortDirection === "asc" ? "asc" : "desc";

  let jcrQuery = `SELECT * FROM [${type}] AS n WHERE ISDESCENDANTNODE(n, '${scopePath}') ORDER BY n.[${orderBy}] ${direction}`;

  if (filter && filter.length > 0) {
    const catIds = filter
      .filter((cat) => cat != null)
      .map((cat) => `'${cat.getIdentifier()}'`)
      .join(", ");
    if (catIds) {
      jcrQuery = jcrQuery.replace(
        " ORDER BY",
        ` AND n.[j:defaultCategory] IN (${catIds}) ORDER BY`
      );
    }
  }

  return { jcrQuery };
}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  "jnt:page": "Pages",
  "lsp:newsArticle": "News Articles",
  "lsp:agendaItem": "Agenda Items",
};

export const getContentTypeLabel = (type?: string): string =>
  type ? CONTENT_TYPE_LABELS[type] || type : "—";
