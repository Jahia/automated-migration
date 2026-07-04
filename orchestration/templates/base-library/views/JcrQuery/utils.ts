import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { RenderContext } from "org.jahia.services.render";

/**
 * base-library JCRQuery — query builder (generalized from lsp:jcrQuery utils).
 * Project-agnostic: no hardcoded content-type label map (the resource bundle
 * supplies labels via the choicelist).
 */
interface BuildQueryInput {
  type?: string;
  criteria?: string;
  sortDirection?: string;
  startNode?: JCRNodeWrapper;
  filter?: JCRNodeWrapper[];
  currentNode: JCRNodeWrapper;
  renderContext: RenderContext;
}

export function buildQuery({
  type,
  criteria,
  sortDirection,
  startNode,
  filter,
  renderContext,
}: BuildQueryInput): { jcrQuery: string } {
  const scopePath = startNode
    ? startNode.getPath()
    : renderContext.getSite().getPath() + "/contents";

  const orderBy = criteria || "jcr:created";
  const direction = sortDirection === "asc" ? "asc" : "desc";
  const nodeType = type || "jnt:content";

  let jcrQuery = `SELECT * FROM [${nodeType}] AS n WHERE ISDESCENDANTNODE(n, '${scopePath}') ORDER BY n.[${orderBy}] ${direction}`;

  if (filter && filter.length > 0) {
    const catIds = filter
      .filter((cat) => cat != null)
      .map((cat) => `'${cat.getIdentifier()}'`)
      .join(", ");
    if (catIds) {
      jcrQuery = jcrQuery.replace(
        " ORDER BY",
        ` AND n.[j:defaultCategory] IN (${catIds}) ORDER BY`,
      );
    }
  }

  return { jcrQuery };
}
