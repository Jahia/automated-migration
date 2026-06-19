import { jahiaComponent } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

/** Centered section title (SXA `simple-title`): optional big faded back-title + small
 *  yellow sub-title above an h2. Use to head a section, e.g. "SIAL en bref". */
jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:simpleTitle', displayName: 'Section Title' },
  function SimpleTitle({ title, backTitle, subTitle, backColor = 'gray' }: Props) {
    return (
      <div className="component simple-title mb-50 mt-50 col-12">
        <div className="component-content">
          {(backTitle || subTitle) && (
            <div className="focus-title">
              {backTitle && <div className={`back-title ${backColor}`}>{backTitle}</div>}
              {subTitle && <div className="sub-title">{subTitle}</div>}
            </div>
          )}
          {title && <h2 className="field-titre">{title}</h2>}
        </div>
      </div>
    );
  }
);
