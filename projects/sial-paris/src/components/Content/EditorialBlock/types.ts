import type { JCRNodeWrapper } from 'org.jahia.services.content';

export interface Props {
  heading?: string;
  body?: string;
  image?: JCRNodeWrapper;
  imageExternalUrl?: string;
  imageAlt?: string;
  imageAlignment?: 'left' | 'right';
}
