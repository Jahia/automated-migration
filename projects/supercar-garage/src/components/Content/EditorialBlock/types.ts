import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface EditorialBlockProps {
  heading?: string;
  subheading?: string;
  image?: JCRNodeWrapper;
  body?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  ctaLabel?: string;
}
