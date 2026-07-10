import { buildNodeUrl, jahiaComponent, useServerContext } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';
import classes from './component.module.css';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:pricingTable', displayName: 'Pricing Table' },
  function PricingTable(props: Props) {
    const { currentNode } = useServerContext();
    const { 'jcr:title': title, intro, columnHeaders, note, ctaLabel } = props;

    const children = Array.from(currentNode.getNodes()) as any[];

    let ctaHref: string | undefined;
    if (props['j:linkType'] === 'internal' && props['j:linknode']) {
      ctaHref = buildNodeUrl(props['j:linknode']);
    } else if (props['j:linkType'] === 'external' && props['j:url']) {
      ctaHref = props['j:url'];
    }

    const headers: string[] = columnHeaders && columnHeaders.length > 0 ? columnHeaders : [];

    return (
      <section className={['component', 'pricing-table', 'col-12', classes.pricingTable].join(' ')}>
        <div className="component-content">
          <div className="container">
          {title && <h2 className={classes.pricingHeading}>{title}</h2>}
          {intro && (
            <div
              className={classes.pricingIntro}
              dangerouslySetInnerHTML={{ __html: intro }}
            />
          )}
          <div className={classes.tableWrapper}>
            <table className={classes.table}>
              {headers.length > 0 && (
                <thead>
                  <tr>
                    <th scope="col" className={classes.emptyCorner}></th>
                    {headers.map((header, i) => (
                      <th key={i} scope="col" className={classes.columnHeader}>
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
              )}
              <tbody>
                {children.map((child: any) => {
                  const rowLabel = child.hasProperty('rowLabel')
                    ? child.getProperty('rowLabel').getString()
                    : undefined;
                  let cells: string[] = [];
                  if (child.hasProperty('cells')) {
                    const vals = child.getProperty('cells').getValues();
                    cells = Array.from(vals).map((v: any) => v.getString());
                  }
                  return (
                    <tr key={child.getIdentifier()} className={classes.row}>
                      <th scope="row" className={classes.rowLabel}>{rowLabel}</th>
                      {cells.map((cell, ci) => (
                        <td key={ci} className={classes.cell}>{cell}</td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {note && (
            <div
              className={classes.pricingNote}
              dangerouslySetInnerHTML={{ __html: note }}
            />
          )}
          {ctaLabel && ctaHref && (
            <div className={classes.ctaWrapper}>
              <a href={ctaHref} className={['btn', 'btn-primary', classes.ctaButton].join(' ')}>
                {ctaLabel}
              </a>
            </div>
          )}
          </div>
        </div>
      </section>
    );
  }
);
