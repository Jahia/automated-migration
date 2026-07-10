import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface ImageBlockProps {
  image?: JCRNodeWrapper;
  imageAltText?: string;
  caption?: string;
}
