import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  logoImage?: JCRNodeWrapper;
  exposantCtaLabel?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  visiteurCtaLabel?: string;
}
