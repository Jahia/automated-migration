import { jahiaComponent } from '@jahia/javascript-modules-library';
import type { InfoCardProps } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:infoCard', displayName: 'Info Card' },
  function InfoCard({ iconClass = 'fa-regular fa-calendar', title, body }: InfoCardProps) {
    return (
      <div className="d-flex position-relative">
        <div className="icon"><i className={iconClass}></i></div>
        {title && <h2>{title}</h2>}
        {body && <div className="card-body" dangerouslySetInnerHTML={{ __html: body }} />}
      </div>
    );
  }
);
