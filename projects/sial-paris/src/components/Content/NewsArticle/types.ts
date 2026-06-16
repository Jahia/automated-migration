import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  thumbnail?: JCRNodeWrapper;
  category?: string;
  publishDate?: string;
  title?: string;
  excerpt?: string;
  body?: string;
}
