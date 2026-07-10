import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface InfoCardProps {
  image?: JCRNodeWrapper;
  imageAltText?: string;
  titre?: string;
  description?: string;
}
