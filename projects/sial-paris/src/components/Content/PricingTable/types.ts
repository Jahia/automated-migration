import type { JCRNodeWrapper } from 'org.jahia.services.content';

export interface PricingTierProps {
  rowLabel?: string;
  cells?: string[];
}

export type Props =
  | { 'jcr:title'?: string; intro?: string; columnHeaders?: string[]; note?: string; ctaLabel?: string; 'j:linkType': 'none' }
  | { 'jcr:title'?: string; intro?: string; columnHeaders?: string[]; note?: string; ctaLabel?: string; 'j:linkType': 'internal'; 'j:linknode'?: JCRNodeWrapper }
  | { 'jcr:title'?: string; intro?: string; columnHeaders?: string[]; note?: string; ctaLabel?: string; 'j:linkType': 'external'; 'j:url'?: string }
  | { 'jcr:title'?: string; intro?: string; columnHeaders?: string[]; note?: string; ctaLabel?: string; 'j:linkType'?: undefined };
