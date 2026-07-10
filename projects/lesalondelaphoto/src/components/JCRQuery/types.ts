import type { JCRNodeWrapper } from "org.jahia.services.content";

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
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
}
