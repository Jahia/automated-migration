import type { JCRNodeWrapper } from "org.jahia.services.content";
import { getNodesByJCRQuery } from "@jahia/javascript-modules-library";
import type { RenderContext } from "org.jahia.services.render";
import { buildQuery } from "./types.js";

const PAGE_SIZE = 6;

export interface QueryState {
  type?: string;
  criteria?: string;
  sortDirection?: string;
  startNode?: JCRNodeWrapper;
  filter?: JCRNodeWrapper[];
  excludeNodes?: JCRNodeWrapper[];
  maxItems?: number;
  loadMore?: boolean;
  currentNode: JCRNodeWrapper;
  renderContext: RenderContext;
}

export function executeQuery({
  type, criteria, sortDirection, startNode, filter, excludeNodes,
  maxItems, loadMore, currentNode, renderContext,
}: QueryState): { nodes: JCRNodeWrapper[]; queryId: string } {
  const { jcrQuery } = buildQuery({
    type, criteria, sortDirection, startNode, filter, excludeNodes,
    currentNode, renderContext,
  });

  const queryContent = getNodesByJCRQuery(
    currentNode.getSession(),
    jcrQuery,
    maxItems && maxItems > 0 ? maxItems : -1,
  );

  const nodes = queryContent ?? [];
  const queryId = currentNode.getIdentifier();

  return { nodes, queryId };
}

export { PAGE_SIZE };
