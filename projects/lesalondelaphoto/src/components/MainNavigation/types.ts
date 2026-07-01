import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface MainNavProps {
  "j:url"?: string;
  "j:linknode"?: string;
  image?: JCRNodeWrapper;
  imageAltText?: string;
}
