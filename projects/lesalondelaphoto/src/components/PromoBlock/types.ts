import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface PromoBlockProps {
  heading?: string;
  description?: string;
  ctaLabel?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  "j:linkTitle"?: string;
}
