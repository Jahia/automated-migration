import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  leftHeading?: string;
  leftImage?: JCRNodeWrapper;
  leftCtaLabel?: string;
  leftLinkNode?: JCRNodeWrapper;
  rightHeading?: string;
  rightImage?: JCRNodeWrapper;
  rightCtaLabel?: string;
  rightLinkNode?: JCRNodeWrapper;
}
