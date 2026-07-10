import type { JCRNodeWrapper } from 'org.jahia.services.content';

export type PersonCardProps =
  | { photo?: JCRNodeWrapper; name?: string; role?: string; bio?: string; linkLabel?: string; 'j:linkType': 'none' }
  | { photo?: JCRNodeWrapper; name?: string; role?: string; bio?: string; linkLabel?: string; 'j:linkType': 'internal'; 'j:linknode'?: JCRNodeWrapper }
  | { photo?: JCRNodeWrapper; name?: string; role?: string; bio?: string; linkLabel?: string; 'j:linkType': 'external'; 'j:url'?: string }
  | { photo?: JCRNodeWrapper; name?: string; role?: string; bio?: string; linkLabel?: string; 'j:linkType'?: undefined };

export interface Props {
  'jcr:title'?: string;
  intro?: string;
}
