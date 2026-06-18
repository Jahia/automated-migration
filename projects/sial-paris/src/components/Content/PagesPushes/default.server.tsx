import { jahiaComponent, Render, useServerContext } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:pagesPushes', displayName: 'Pages Pushes' },
  function PagesPushes({ heading }: Props) {
    const { currentNode } = useServerContext();
    const children = Array.from(currentNode.getNodes()) as any[];
    return (
      <div className="component content container-bp pages-pushes hover basic-vertical-space col-12">
        <div className="component-content">
          {heading && <h2 className="mb-4">{heading}</h2>}
          <div className="row">
            {children.map((child: any) => (
              <Render key={child.getIdentifier()} node={child} />
            ))}
          </div>
        </div>
      </div>
    );
  }
);
