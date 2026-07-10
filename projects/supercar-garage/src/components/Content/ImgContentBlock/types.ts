import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface ImgContentBlockProps {
  iconClass?: string;
  image?: JCRNodeWrapper;
  heading?: string;
  body?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  ctaLabel?: string;
}
