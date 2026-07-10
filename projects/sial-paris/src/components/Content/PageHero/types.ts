import type { JCRNodeWrapper } from 'org.jahia.services.content';

export interface Props {
  heading?: string;
  subtitle?: string;
  backgroundImage?: JCRNodeWrapper;
  backgroundImageUrl?: string;
  backgroundColor?: string;
}
