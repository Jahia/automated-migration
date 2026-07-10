import { jahiaComponent, Render, useServerContext } from '@jahia/javascript-modules-library';
import type { Props } from './types.js';

jahiaComponent(
  { componentType: 'view', nodeType: 'sialp:pagesPushes', displayName: 'Pages Pushes' },
  function PagesPushes({ heading }: Props) {
    const { currentNode, renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();
    const children = Array.from(currentNode.getNodes()) as any[];
    // In edit mode Page Builder wraps each item, so the Bootstrap row/col grid
    // breaks (cards squeeze left). Lay the row out as a responsive CSS grid here —
    // its direct children are the edit wrappers, so the cards present as a clean
    // grid regardless of the wrapping. Live keeps the normal Bootstrap row.
    const rowStyle = isEdit
      ? { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "1.5rem" }
      : undefined;
    return (
      <div className="component content container-bp pages-pushes hover basic-vertical-space col-12">
        <div className="component-content">
          {heading && <h2 className="mb-4">{heading}</h2>}
          <div className="row" style={rowStyle}>
            {children.map((child: any) => (
              <Render key={child.getIdentifier()} node={child} />
            ))}
          </div>
        </div>
      </div>
    );
  }
);
