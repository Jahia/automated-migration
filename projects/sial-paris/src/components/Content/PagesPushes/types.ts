import type { JCRNodeWrapper } from 'org.jahia.services.content';

export interface PagesPushesItemProps {
  image?: JCRNodeWrapper;
  imageExternalUrl?: string;
  imageAlt?: string;
  title?: string;
  description?: string;
  linkUrl?: string;
}

export interface Props {
  heading?: string;
}
