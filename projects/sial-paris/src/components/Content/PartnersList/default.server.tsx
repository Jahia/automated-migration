import { Island, buildNodeUrl, jahiaComponent, useServerContext } from '@jahia/javascript-modules-library';
import type { EntryProps, Props } from './types.js';
import PartnersFilter from './partnersFilter.client.jsx';
import classes from './partnersGrid.module.css';

const CATEGORY_LABELS: Record<string, string> = {
  animations: 'Animations',
  institutionnels: 'Institutionnels',
  medias: 'Médias',
  salons: 'Salons',
  sialInsights: 'SIAL Insights',
};
const CATEGORY_ORDER = ['animations', 'institutionnels', 'medias', 'salons', 'sialInsights'];

/** A single partner row (used standalone / in the detailed list view). */
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

/** Partner logo wall with category filter tabs (Animations / Institutionnels / Médias / Salons / SIAL Insights). */
jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:partnersList', displayName: 'Partners List' },
  function PartnersList({ heading }: Props) {
    const { currentNode } = useServerContext();
    const children = Array.from(currentNode.getNodes()) as any[];

    const catOf = (ch: any) =>
      ch.hasProperty('partnerCategory') ? ch.getProperty('partnerCategory').getString() : '';
    const present = CATEGORY_ORDER.filter((c) => children.some((ch) => catOf(ch) === c)).map((c) => ({
      key: c,
      label: CATEGORY_LABELS[c] ?? c,
    }));

    return (
      <div className="component partners-2-list container-bp col-12">
        <div className="component-content">
          {heading && <h2 className="field-title">{heading}</h2>}
          <Island component={PartnersFilter} props={{ categories: present }}>
            <div className={classes.grid}>
              {children.map((ch) => {
                const cat = catOf(ch);
                const title = ch.hasProperty('title') ? ch.getProperty('title').getString() : '';
                let logoUrl: string | null = null;
                if (ch.hasProperty('logo')) {
                  try {
                    logoUrl = buildNodeUrl(ch.getProperty('logo').getNode());
                  } catch (_) {
                    /* missing ref */
                  }
                }
                if (!logoUrl && ch.hasProperty('logoExternalUrl')) {
                  logoUrl = ch.getProperty('logoExternalUrl').getString() || null;
                }
                return (
                  <figure key={ch.getIdentifier()} className={classes.item} data-category={cat}>
                    {logoUrl && <img src={logoUrl} alt={title} className={classes.logo} loading="lazy" />}
                    {title && <figcaption className={classes.name}>{title}</figcaption>}
                  </figure>
                );
              })}
            </div>
          </Island>
        </div>
      </div>
    );
  }
);
