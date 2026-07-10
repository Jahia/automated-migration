import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface PartnerLogoProps {
  image?: JCRNodeWrapper;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  altText?: string;
}
