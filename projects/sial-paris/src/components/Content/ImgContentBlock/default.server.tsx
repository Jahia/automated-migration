import { buildNodeUrl, jahiaComponent } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:imgContentBlock', displayName: 'Image Content Block' },
  function ImgContentBlock({ image, imageExternalUrl, imageAlt, watermarkWord, heading, body, ctaLabel, ctaUrl }: Props) {
    const imgUrl = image ? buildNodeUrl(image) : (imageExternalUrl || null);
    return (
      <div className="component content img-content-block-l mb-50 col-12">
        <div className="component-content">
          <div className="div1 bg-gray-1"></div>
          <div className="container-bp">
            <div className="row">
              <div className="col-md-6">
                {imgUrl && <img src={imgUrl} alt={imageAlt || ''} className="img-cover basic-radius w-100" />}
              </div>
              <div className="col-md-6 bg-gray-1">
                {watermarkWord && <div className="simple-title">{watermarkWord}</div>}
                {heading && <div className="field-title"><h2>{heading}</h2></div>}
                {body && <div className="field-body" dangerouslySetInnerHTML={{ __html: body }} />}
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
