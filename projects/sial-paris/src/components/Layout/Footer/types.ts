import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  newsletterHeading?: string;
  newsletterPlaceholder?: string;
  gdprText?: string;
  sialLogo?: JCRNodeWrapper;
  comexposiumLogo?: JCRNodeWrapper;
  copyrightText?: string;
}
