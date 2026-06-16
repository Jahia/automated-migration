import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  backgroundImage?: JCRNodeWrapper;
  badge?: string;
  heading?: string;
  body?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  ctaLabel?: string;
}
