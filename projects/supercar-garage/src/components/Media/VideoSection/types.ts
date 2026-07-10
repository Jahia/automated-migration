import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface VideoSectionProps {
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  caption?: string;
  description?: string;
}
