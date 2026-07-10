import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface NewsArticleProps {
  "jcr:title"?: string;
  publishDate?: string;
  image?: JCRNodeWrapper;
  summary?: string;
  bodyContent?: string;
  author?: string;
}
