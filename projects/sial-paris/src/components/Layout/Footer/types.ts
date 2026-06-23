import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  communityText?: string;
  faqText?: string;
  newsletterHeading?: string;
  newsletterPlaceholder?: string;
  newsletterLabel?: string;
  gdprText?: string;
  organisedByLabel?: string;
  sialLogo?: JCRNodeWrapper;
  comexposiumLogo?: JCRNodeWrapper;
  stockfoodLogo?: JCRNodeWrapper;
  copyrightText?: string;
  submitButtonLabel?: string;
}
