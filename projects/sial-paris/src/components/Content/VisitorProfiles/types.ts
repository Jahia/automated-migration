import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  icon?: JCRNodeWrapper;
  heading?: string;
  description?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  ctaLabel?: string;
}
