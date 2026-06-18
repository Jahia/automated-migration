import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  backgroundImage?: JCRNodeWrapper;
  icon?: JCRNodeWrapper;
  label?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  heading?: string;
}
