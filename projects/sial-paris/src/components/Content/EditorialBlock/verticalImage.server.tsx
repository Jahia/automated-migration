import { jahiaComponent, buildNodeUrl } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

/**
 * Editorial block with a narrow portrait image beside wide text
 * (SXA `content-block-vertical-image left-img`): image col-4, text col-7.
 * Use for posters/affiches and tall visuals.
 */
jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:editorialBlock', name: 'verticalImage', displayName: 'Editorial block — vertical image' },
  function EditorialBlockVertical({ heading, body, image, imageExternalUrl, imageAlt, ctaLabel, ctaUrl, darkBackground }: Props) {
    const imgUrl = image ? buildNodeUrl(image) : (imageExternalUrl || null);
    return (
      <div className={`component content-block-vertical-image left-img col-12${darkBackground ? ' background-primary' : ''}`}>
        <div className="component-content">
          <div className="container-bp">
            <div className="row justify-content-between">
              <div className="col-md-5 col-lg-4">
                {imgUrl && <img src={imgUrl} alt={imageAlt || heading || ''} className="img-cover basic-radius w-100" />}
              </div>
              <div className="col-md-7 align-self-center">
                {heading && <h2 className="mb-20 field-title">{heading}</h2>}
                {body && <div className="field-description" dangerouslySetInnerHTML={{ __html: body }} />}
                {ctaLabel && (
                  <div className="field-cta">
                    <a href={ctaUrl || '#'} className="btn btn-primary">{ctaLabel}</a>
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
