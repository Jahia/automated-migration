import type { JCRNodeWrapper } from 'org.jahia.services.content';

export interface EntryProps {
  logo?: JCRNodeWrapper;
  logoExternalUrl?: string;
  "jcr:title"?: string;
  body?: string;
  linkLabel?: string;
  linkUrl?: string;
  partnerCategory?: string;
}

export interface Props {
  heading?: string;
}
