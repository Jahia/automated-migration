import { jahiaComponent } from '@jahia/javascript-modules-library';
import { LucideIcon } from '../../shared/LucideIcon.js';
import type { InfoCardProps } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:infoCard', displayName: 'Info Card' },
  function InfoCard({ iconClass = 'calendar', "jcr:title": title, body }: InfoCardProps) {
    return (
      <div className="d-flex position-relative">
        <div className="icon"><LucideIcon name={iconClass} size={28} /></div>
        {title && <h2>{title}</h2>}
        {body && <div className="card-body" dangerouslySetInnerHTML={{ __html: body }} />}
      </div>
    );
  }
);
