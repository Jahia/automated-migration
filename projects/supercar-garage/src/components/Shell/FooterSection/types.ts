import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface FooterSectionProps {
  socialHeading?: string;
  newsletterLabel?: string;
  newsletterPlaceholder?: string;
  newsletterConsentLabel?: string;
  newsletterSubmitLabel?: string;
  partnerLogo1?: JCRNodeWrapper;
  partnerLogo2?: JCRNodeWrapper;
  partnerLogo3?: JCRNodeWrapper;
  partnerLabel1?: string;
  partnerLabel2?: string;
  partnerLabel3?: string;
  legalPlanSite?: string;
  legalMentions?: string;
  legalData?: string;
  legalCookies?: string;
}
