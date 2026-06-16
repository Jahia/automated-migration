import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  leftHeading?: string;
  leftImage?: JCRNodeWrapper;
  leftCtaLabel?: string;
  leftLinkType?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  rightHeading?: string;
  rightImage?: JCRNodeWrapper;
  rightCtaLabel?: string;
  rightLinkType?: string;
}
