import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  heading?: string;
  tagline?: string;
  videoUrl?: string;
  thumbnailImage?: JCRNodeWrapper;
}
