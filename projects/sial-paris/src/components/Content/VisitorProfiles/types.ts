import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  icon?: JCRNodeWrapper;
  iconClass?: string;
  heading?: string;
  description?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  ctaLabel?: string;
}
