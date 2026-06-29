import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface PartnerItemProps {
  logo?: JCRNodeWrapper;
  name?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  "j:linkTitle"?: string;
}
