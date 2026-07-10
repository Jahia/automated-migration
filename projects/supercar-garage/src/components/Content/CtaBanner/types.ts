import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface CtaBannerProps {
  ctaLabel?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
}
