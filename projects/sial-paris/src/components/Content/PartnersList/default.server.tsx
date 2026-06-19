import { RenderChildren, buildNodeUrl, jahiaComponent } from '@jahia/javascript-modules-library';
import type { EntryProps, Props } from './types.js';

/** A single partner row: logo (col-4) + title + description + link (col-8) — SXA `partners-2-list` item. */
jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:partnerEntry', displayName: 'Partner Entry' },
  function PartnerEntry({ logo, logoExternalUrl, title, body, linkLabel, linkUrl }: EntryProps) {
    const logoUrl = logo ? buildNodeUrl(logo) : (logoExternalUrl || null);
    return (
      <div className="row align-items-center">
        <div className="col-md-4">
          {logoUrl && <img src={logoUrl} alt={title || ''} className="img-logo" />}
        </div>
        <div className="col-md-8">
          {title && <h3 className="field-titre">{title}</h3>}
          {body && <div className="mb-20 field-description" dangerouslySetInnerHTML={{ __html: body }} />}
          {linkLabel && (
            <div className="link-secondary field-lien-partenaire-2">
              <a href={linkUrl || '#'}>{linkLabel}</a>
            </div>
          )}
        </div>
      </div>
    );
  }
);

/** Detailed partners list (SXA `partners-2-list`): each entry is a logo + description + link. */
jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:partnersList', displayName: 'Partners List' },
  function PartnersList({ heading }: Props) {
    return (
      <div className="component partners-2-list container-bp col-12">
        <div className="component-content">
          {heading && <h2 className="field-title">{heading}</h2>}
          <RenderChildren />
        </div>
      </div>
    );
  }
);
