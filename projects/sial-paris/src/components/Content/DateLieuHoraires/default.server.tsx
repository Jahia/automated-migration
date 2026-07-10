import { jahiaComponent, Render, useServerContext } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:dateLieuHoraires', displayName: 'Date Lieu Horaires' },
  function DateLieuHoraires({ leadText, ctaLabel, ctaUrl }: Props) {
    const { currentNode } = useServerContext();
    const children = currentNode.getNodes();
    return (
      <div className="component content date-lieu-horaires col-12">
        {leadText && <div className="col-12 mb-4" dangerouslySetInnerHTML={{ __html: leadText }} />}
        {ctaLabel && (
          <div className="col-12 text-center mb-4">
            <a href={ctaUrl || '#'} className="btn btn-primary btn-lg">{ctaLabel}</a>
          </div>
        )}
        <div className="component-content">
          {Array.from(children).map((child: any) => (
            <div key={child.getIdentifier()} className="col-md-4">
              <Render node={child} />
            </div>
          ))}
        </div>
      </div>
    );
  }
);
