import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  heading?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  ctaLabel?: string;
  maxItems?: number;
}
