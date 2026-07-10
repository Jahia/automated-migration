import { buildNodeUrl, jahiaComponent } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:pageHero', displayName: 'Page Hero' },
  function PageHero({ heading, subtitle, backgroundImage, backgroundImageUrl }: Props) {
    const imgUrl = backgroundImage ? buildNodeUrl(backgroundImage) : (backgroundImageUrl || null);
    return (
      <div className="component title banner-title3 container text-center text-white small-banner col-12">
        <div className="component-content">
          {imgUrl && <img src={imgUrl} alt="" aria-hidden="true" />}
          {/*
            Stack subtitle + heading vertically. .fields-container is flex-column
            with a gap, so direct children stack and stay centered over the image.
            Do NOT wrap in .focus-title with a .back-title — that CSS absolutely
            centers the back-title over the heading, making them overlap.
          */}
          <div className="fields-container">
            {subtitle && <div className="sub-title field-arriere-titre">{subtitle}</div>}
            {heading && <h1 className="field-titre">{heading}</h1>}
          </div>
        </div>
      </div>
    );
  }
);
