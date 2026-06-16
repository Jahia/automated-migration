import type { JCRNodeWrapper } from "org.jahia.services.content";

export interface Props {
  eventName?: string;
  city?: string;
  eventDates?: string;
  "j:linkType"?: string;
  "j:linknode"?: JCRNodeWrapper;
  "j:url"?: string;
  heading?: string;
}
