import type { JCRNodeWrapper } from 'org.jahia.services.content';

export interface InfoCardProps {
  iconClass?: string;
  title?: string;
  body?: string;
}

export interface Props {
  leadText?: string;
  ctaLabel?: string;
  ctaUrl?: string;
}
