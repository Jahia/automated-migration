import { jahiaComponent } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

/** Previous / next page navigation at the foot of editorial pages (SXA `previous-next`). */
jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:previousNext', displayName: 'Previous / Next' },
  function PreviousNext({ prevLabel, prevUrl, nextLabel, nextUrl }: Props) {
    return (
      <div className="component container col-12 previous-next">
        <div className="component-content">
          <div className="row">
            <div className="component link col-6">
              <div className="component-content">
                {prevLabel && (
                  <div className="row align-items-center">
                    <a href={prevUrl || '#'} className="field-title">{prevLabel}</a>
                  </div>
                )}
              </div>
            </div>
            <div className="component link col-6">
              <div className="component-content">
                {nextLabel && (
                  <div className="row align-items-center justify-content-end">
                    <a href={nextUrl || '#'} className="field-title">{nextLabel}</a>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
);
