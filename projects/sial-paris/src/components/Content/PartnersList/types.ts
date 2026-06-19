import type { JCRNodeWrapper } from 'org.jahia.services.content';

export interface EntryProps {
  logo?: JCRNodeWrapper;
  logoExternalUrl?: string;
  title?: string;
  body?: string;
  linkLabel?: string;
  linkUrl?: string;
}

export interface Props {
  heading?: string;
}
