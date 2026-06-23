import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  tag?: string;
  image?: JCRNodeWrapper;
  imageExternalUrl?: string;
  surtitle?: string;
  heading?: string;
  intro?: string;
  excerpt?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  ctaLabel?: string;
}
