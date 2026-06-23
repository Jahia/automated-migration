import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  overline?: string;
  heading?: string;
  icon?: string;
  number?: string;
  unit?: string;
  label?: string;
  ctaLabel?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
}
