import { getChildNodes, jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { CardGridProps } from "./types.js";

function parseColumns(raw: unknown): number {
  const n = Number(raw);
  if (Number.isNaN(n) || n < 1) return 3;
  return Math.min(4, n);
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:cardGrid",
    displayName: "Card Grid",
  },
  ({ heading, columns: rawCols }: CardGridProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const cols = parseColumns(rawCols);
    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:hero"),
    );

    return (
      <div className="component picture-grid container-bp col-12">
        <div className="component-content">
          {heading && (
            <div className="component simple-title mb-50 mt-50 col-12">
              <div className="component-content">
                <div className="focus-title" />
                <h2 className="field-titre">{heading}</h2>
              </div>
            </div>
          )}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
              gap: "24px",
            }}
          >
            {children.map((child) => (
              <div key={child.getIdentifier()}>
                <Render node={child as JCRNodeWrapper} view="card" readOnly />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  },
);
