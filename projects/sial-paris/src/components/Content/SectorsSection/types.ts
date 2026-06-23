import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  backgroundImage?: JCRNodeWrapper;
  icon?: JCRNodeWrapper;
  iconClass?: string;
  label?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  heading?: string;
}
