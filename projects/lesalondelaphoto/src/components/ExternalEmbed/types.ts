import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface ExternalEmbedProps {
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  "j:linkTitle"?: string;
  embedTitle?: string;
  embedHeight?: number;
}
