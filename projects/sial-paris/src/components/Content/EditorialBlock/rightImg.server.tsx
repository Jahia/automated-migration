import { jahiaComponent, buildNodeUrl } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

/** Editorial block, text-left / image-right (SXA `content-block right-img`). */
jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:editorialBlock', name: 'rightImg', displayName: 'Editorial block — image right' },
  function EditorialBlockRight({ heading, body, image, imageExternalUrl, imageAlt, ctaLabel, ctaUrl, darkBackground }: Props) {
    const imgUrl = image ? buildNodeUrl(image) : (imageExternalUrl || null);
    return (
      <div className={`component content-block right-img col-12${darkBackground ? ' background-primary' : ''}`}>
        <div className="component-content">
          <div className="container-bp">
            <div className="row align-items-center">
              <div className="col-md-6">
                {heading && <h2 className="mb-20 field-title">{heading}</h2>}
                {body && <div className="field-description" dangerouslySetInnerHTML={{ __html: body }} />}
                {ctaLabel && (
                  <div className="field-cta">
                    <a href={ctaUrl || '#'} className="btn btn-primary">{ctaLabel}</a>
                  </div>
                )}
              </div>
              <div className="col-md-6">
                {imgUrl && <img src={imgUrl} alt={imageAlt || heading || ''} className="img-cover basic-radius w-100" />}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
);
