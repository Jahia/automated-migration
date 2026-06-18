import { jahiaComponent, buildNodeUrl } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:editorialBlock', name: 'default', displayName: 'Editorial Block' },
  function EditorialBlock({ heading, body, image, imageExternalUrl, imageAlt, imageAlignment = 'left' }: Props) {
    const imgUrl = image ? buildNodeUrl(image) : (imageExternalUrl || null);
    const altText = imageAlt || heading || '';
    const isLeft = imageAlignment === 'left';

    return (
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '3rem 2rem' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2rem', alignItems: 'flex-start' }}>
        {isLeft && imgUrl && (
          <div style={{ flex: '0 0 40%', maxWidth: '40%' }}>
            <img src={imgUrl} alt={altText} style={{ width: '100%', height: 'auto', display: 'block' }} />
          </div>
        )}
        <div style={{ flex: '1 1 55%' }}>
          {heading && (
            <h2 style={{ fontSize: '1.75rem', fontWeight: '700', color: '#1a2b4a', marginBottom: '1rem', lineHeight: '1.3' }}>
              {heading}
            </h2>
          )}
          {body && (
            <div
              style={{ fontSize: '1rem', lineHeight: '1.7', color: '#333' }}
              dangerouslySetInnerHTML={{ __html: body }}
            />
          )}
        </div>
        {!isLeft && imgUrl && (
          <div style={{ flex: '0 0 40%', maxWidth: '40%' }}>
            <img src={imgUrl} alt={altText} style={{ width: '100%', height: 'auto', display: 'block' }} />
          </div>
        )}
      </div>
      </div>
    );
  }
);
