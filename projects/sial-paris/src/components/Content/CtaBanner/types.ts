import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  heading?: string;
  subtext?: string;
  ctaLabel?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  backgroundColor?: string;
}
