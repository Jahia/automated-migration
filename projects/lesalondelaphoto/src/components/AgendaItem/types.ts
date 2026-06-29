import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface AgendaItemProps {
  "jcr:title"?: string;
  image?: JCRNodeWrapper;
  imageAltText?: string;
  date?: string;
  location?: string;
  body?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  "j:linkTitle"?: string;
}
