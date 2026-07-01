import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface FooterProps {
  footerText?: string;
  image?: JCRNodeWrapper;
  imageAltText?: string;
}
