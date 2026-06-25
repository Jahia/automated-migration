import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface QuickLinkCardProps {
  iconClass?: string;
  heading?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
}
