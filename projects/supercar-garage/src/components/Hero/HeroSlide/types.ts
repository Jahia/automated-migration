import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface HeroSlideProps {
  image?: JCRNodeWrapper;
  smallTitle?: string;
  body?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  ctaLabel?: string;
}
