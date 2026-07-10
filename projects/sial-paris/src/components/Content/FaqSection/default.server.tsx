import { jahiaComponent, Render, useServerContext } from '@jahia/javascript-modules-library';
import type { FaqItemProps, Props } from './types.js';
import classes from './component.module.css';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:faqItem', displayName: 'FAQ Item' },
  function FaqItem({ question, answer }: FaqItemProps) {
    return (
      <details className={classes.faqItem}>
        <summary className={classes.faqQuestion}>{question}</summary>
        {answer && (
          <div
            className={classes.faqAnswer}
            dangerouslySetInnerHTML={{ __html: answer }}
          />
        )}
      </details>
    );
  }
);

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:faqSection', displayName: 'FAQ Section' },
  function FaqSection({ 'jcr:title': title, intro }: Props) {
    const { currentNode } = useServerContext();
    const children = Array.from(currentNode.getNodes()) as any[];
    return (
      <section className={['component', 'faq-section', 'col-12', classes.faqSection].join(' ')}>
        <div className="component-content">
          <div className="container">
            {title && <h2 className={classes.faqHeading}>{title}</h2>}
            {intro && (
              <div
                className={classes.faqIntro}
                dangerouslySetInnerHTML={{ __html: intro }}
              />
            )}
            <div className={classes.faqList}>
              {children.map((child: any) => (
                <Render key={child.getIdentifier()} node={child} />
              ))}
            </div>
          </div>
        </div>
      </section>
    );
  }
);
