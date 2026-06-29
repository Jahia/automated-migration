import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface EditorialBlockProps {
  heading?: string;
  body?: string;
  image?: JCRNodeWrapper;
  imageAltText?: string;
  imagePosition?: string;
}
