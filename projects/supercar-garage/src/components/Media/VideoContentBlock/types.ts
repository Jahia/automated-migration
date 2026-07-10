import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface VideoContentBlockProps {
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  heading?: string;
  body?: string;
}
