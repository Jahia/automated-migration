import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  thumbnail?: JCRNodeWrapper;
  publishDate?: string;
  /** Inherited from mix:title (i18n). The node title shown in jContent. */
  "jcr:title"?: string;
  excerpt?: string;
  body?: string;
}
