import type { JCRNodeWrapper } from 'org.jahia.services.content';

export interface Props {
  image?: JCRNodeWrapper;
  imageExternalUrl?: string;
  imageAlt?: string;
  watermarkWord?: string;
  heading?: string;
  body?: string;
  ctaLabel?: string;
  ctaUrl?: string;
}
