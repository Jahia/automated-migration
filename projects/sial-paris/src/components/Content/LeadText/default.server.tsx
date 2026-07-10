import { jahiaComponent } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:leadText', displayName: 'Lead Text' },
  function LeadText({ text }: Props) {
    if (!text) return null;
    return (
      <div className="component content col-12">
        <div className="component-content">
          <div className="container">
            <div className="row">
              <div className="col-12 col-md-10 offset-md-1">
                <div className="field-lead-text" dangerouslySetInnerHTML={{ __html: text }} />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
);
