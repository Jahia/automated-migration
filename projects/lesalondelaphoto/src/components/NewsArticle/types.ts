import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface NewsArticleProps {
  "jcr:title"?: string;
  image?: JCRNodeWrapper;
  imageAltText?: string;
  publishDate?: string;
  summary?: string;
  body?: string;
  "j:tagList"?: string[];
}
