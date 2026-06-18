import { buildNodeUrl, jahiaComponent } from '@jahia/javascript-modules-library';

export interface ItemProps {
  image?: any;
  imageExternalUrl?: string;
  imageAlt?: string;
  title?: string;
  description?: string;
  linkUrl?: string;
}

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:pagesPushesItem', displayName: 'Pages Pushes Item' },
  function PagesPushesItem({ image, imageExternalUrl, imageAlt, title, description, linkUrl }: ItemProps) {
    const imgUrl = image ? buildNodeUrl(image) : (imageExternalUrl || null);
    return (
      <div className="col-md-3 col-sm-6">
        <a href={linkUrl || '#'}>
          <div className="card">
            {imgUrl && (
              <div className="field-image-push">
                <img src={imgUrl} alt={imageAlt || ''} />
              </div>
            )}
            <div className="description">
              {title && <h3>{title}</h3>}
              {description && <div className="field-content">{description}</div>}
            </div>
          </div>
        </a>
      </div>
    );
  }
);
