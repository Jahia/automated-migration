import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface MainNavigationProps {
  logo?: JCRNodeWrapper;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  eventDate?: string;
  eventVenue?: string;
  ctaPrimaryLabel?: string;
  ctaSecondaryLabel?: string;
}
