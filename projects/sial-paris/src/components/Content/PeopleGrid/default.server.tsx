import { buildNodeUrl, jahiaComponent, Render, useServerContext } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';
import classes from './component.module.css';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:peopleGrid', displayName: 'People Grid' },
  function PeopleGrid({ 'jcr:title': title, intro }: Props) {
    const { currentNode } = useServerContext();
    const children = Array.from(currentNode.getNodes()) as any[];
    return (
      <section className={['component', 'people-grid', 'col-12', classes.peopleGrid].join(' ')}>
        <div className="component-content">
          <div className="container">
            {title && <h2 className={classes.gridHeading}>{title}</h2>}
            {intro && (
              <div
                className={classes.gridIntro}
                dangerouslySetInnerHTML={{ __html: intro }}
              />
            )}
            <ul className={classes.cardList} role="list">
              {children.map((child: any) => (
                <li key={child.getIdentifier()} className={classes.cardItem}>
                  <Render node={child} />
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    );
  }
);

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:personCard', displayName: 'Person Card' },
  function PersonCard(props: any) {
    const { photo, name, role, bio, linkLabel } = props;
    const linkType = props['j:linkType'];
    const linkNode = props['j:linknode'];
    const linkUrl = props['j:url'];

    let href: string | undefined;
    if (linkType === 'internal' && linkNode) {
      href = buildNodeUrl(linkNode);
    } else if (linkType === 'external' && linkUrl) {
      href = linkUrl;
    }

    return (
      <article className={classes.personCard}>
        {photo && (
          <div className={classes.photoWrapper}>
            <Render node={photo} view="thumbnail" />
          </div>
        )}
        <div className={classes.cardBody}>
          {name && <h3 className={classes.personName}>{name}</h3>}
          {role && <p className={classes.personRole}>{role}</p>}
          {bio && (
            <div
              className={classes.personBio}
              dangerouslySetInnerHTML={{ __html: bio }}
            />
          )}
          {linkLabel && href && (
            <a href={href} className={classes.personLink}>
              {linkLabel}
            </a>
          )}
        </div>
      </article>
    );
  }
);
