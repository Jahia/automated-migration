import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface PressReleaseProps {
  "jcr:title"?: string;
  publishDate?: string;
  image?: JCRNodeWrapper;
  summary?: string;
  bodyContent?: string;
  pressContact?: string;
}
