import { buildNodeUrl, jahiaComponent, useServerContext } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';
import classes from './tabbed.module.css';

const CATEGORY_LABELS: Record<string, string> = {
  animations: 'Animations',
  institutionnels: 'Institutionnels',
  medias: 'Medias',
  salons: 'Salons',
  sialInsights: 'SIAL Insights',
};

function resolveLogoUrl(child: any): string | null {
  // Try weakreference logo first
  if (child.hasProperty('logo')) {
    try {
      const logoId = child.getProperty('logo').getString();
      const logoNode = child.getSession().getNodeByIdentifier(logoId);
      if (logoNode) return buildNodeUrl(logoNode);
    } catch (_) {
      // fall through to external URL
    }
  }
  // Fallback to external URL field
  if (child.hasProperty('logoExternalUrl')) {
    const ext = child.getProperty('logoExternalUrl').getString();
    if (ext) return ext;
  }
  return null;
}

function renderEntry(child: any) {
  const logoUrl = resolveLogoUrl(child);
  const title = child.hasProperty('jcr:title') ? child.getProperty('jcr:title').getString() : undefined;
  const body = child.hasProperty('body') ? child.getProperty('body').getString() : undefined;
  const linkLabel = child.hasProperty('linkLabel') ? child.getProperty('linkLabel').getString() : undefined;
  const linkUrl = child.hasProperty('linkUrl') ? child.getProperty('linkUrl').getString() : undefined;

  return (
    <li key={child.getIdentifier()} className={classes.partnerItem}>
      <div className={classes.partnerRow}>
        <div className={classes.logoCol}>
          {logoUrl && <img src={logoUrl} alt={title || ''} className={classes.logoImg} />}
        </div>
        <div className={classes.contentCol}>
          {title && <h4 className={classes.partnerTitle}>{title}</h4>}
          {body && (
            <div className={classes.partnerBody} dangerouslySetInnerHTML={{ __html: body }} />
          )}
          {linkLabel && linkUrl && (
            <a href={linkUrl} className={classes.partnerLink}>{linkLabel}</a>
          )}
        </div>
      </div>
    </li>
  );
}

jahiaComponent(
  {
    componentType: 'view',
    nodeType: 'sialp:partnersList',
    name: 'tabbed',
    displayName: 'Partners List (Tabbed by Category)',
  },
  function PartnersListTabbed({ heading }: Props) {
    const { currentNode } = useServerContext();
    const children = Array.from(currentNode.getNodes()) as any[];

    // Group children by partnerCategory
    const grouped: Record<string, any[]> = {};
    const uncategorised: any[] = [];

    for (const child of children) {
      const cat =
        child.hasProperty('partnerCategory')
          ? child.getProperty('partnerCategory').getString()
          : '';
      if (cat) {
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(child);
      } else {
        uncategorised.push(child);
      }
    }

    const categories = Object.keys(grouped);

    return (
      <div
        className={[
          'component',
          'partners-tabbed',
          'container-bp',
          'col-12',
          classes.root,
        ].join(' ')}
      >
        <div className="component-content">
          {heading && <h2 className={classes.heading}>{heading}</h2>}

          {categories.map((cat) => (
            <section
              key={cat}
              className={classes.categorySection}
              aria-labelledby={`cat-heading-${cat}`}
            >
              <h3
                id={`cat-heading-${cat}`}
                className={classes.categoryHeading}
              >
                {CATEGORY_LABELS[cat] ?? cat}
              </h3>
              <ul className={classes.partnerList} role="list">
                {grouped[cat].map((child: any) => renderEntry(child))}
              </ul>
            </section>
          ))}

          {uncategorised.length > 0 && (
            <section className={classes.categorySection} aria-label="Autres partenaires">
              <ul className={classes.partnerList} role="list">
                {uncategorised.map((child: any) => renderEntry(child))}
              </ul>
            </section>
          )}
        </div>
      </div>
    );
  }
);
