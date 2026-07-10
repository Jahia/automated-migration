import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface HeroProps {
  image?: JCRNodeWrapper;
  imageAltText?: string;
  heading?: string;
  subheading?: string;
  ctaLabel?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  "j:linkTitle"?: string;
}
