import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  logo?: JCRNodeWrapper;
  logoExternalUrl?: string;
  partnerName?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  heading?: string;
}
