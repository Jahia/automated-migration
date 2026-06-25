import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { RenderContext } from "org.jahia.services.render";

export interface JcrQueryProps {
  "jcr:title"?: string;
  type?: string;
  criteria?: string;
  sortDirection?: string;
  maxItems?: number;
  startNode?: JCRNodeWrapper;
  excludeNodes?: JCRNodeWrapper[];
  filter?: JCRNodeWrapper[];
  noResultText?: string;
  "j:subNodesView"?: string;
  "j:linkType"?: string;
  loadMore?: boolean;
  categoryFilter?: boolean;
  "j:url"?: string;
  "j:linknode"?: JCRNodeWrapper;
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
}: {
  type?: string;
  criteria?: string;
  sortDirection?: string;
  startNode?: JCRNodeWrapper;
  filter?: JCRNodeWrapper[];
  excludeNodes?: JCRNodeWrapper[];
  currentNode: JCRNodeWrapper;
  renderContext: RenderContext;
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
      .map((n) => `'${n.getIdentifier()}'`)
      .join(", ");
    if (catIds)
      jcrQuery = jcrQuery.replace(
        " ORDER BY",
        ` AND n.[j:defaultCategory] IN (${catIds}) ORDER BY`,
      );
  }

  return { jcrQuery };
}
