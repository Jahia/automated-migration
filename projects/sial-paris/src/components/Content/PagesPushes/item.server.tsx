import { buildNodeUrl, jahiaComponent } from '@jahia/javascript-modules-library';
import type { RenderContext } from 'org.jahia.services.render';

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
  function PagesPushesItem(
    { image, imageExternalUrl, imageAlt, title, description, linkUrl }: ItemProps,
    { renderContext }: { renderContext: RenderContext },
  ) {
    const isEdit = renderContext.isEditMode();
    const imgUrl = image ? buildNodeUrl(image) : (imageExternalUrl || null);
    return (
      // Edit mode: drop the Bootstrap cols and fill the grid cell the section
      // lays out (see PagesPushes) — avoids the card squeezing to 25% of its
      // edit wrapper. Live keeps the Bootstrap col grid.
      <div
        className={isEdit ? '' : 'col-md-3 col-sm-6'}
        style={isEdit ? { width: '100%' } : undefined}
      >
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
