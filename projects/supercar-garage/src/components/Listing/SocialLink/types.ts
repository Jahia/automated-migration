import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface SocialLinkProps {
  platform?: string;
  iconClass?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
}
