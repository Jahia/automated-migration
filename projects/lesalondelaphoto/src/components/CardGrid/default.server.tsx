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

    // Faithful transcription of the reference `.component.picture-grid.container-bp.col-12`:
    // cards render DIRECTLY in .component-content (the card view emits the <div> wrapper).
    // No inline CSS grid — the imported theme CSS lays the picture-grid out (support-create-view).
    void cols;
    return (
      <div className="component picture-grid container-bp col-12">
        <div className="component-content">
          {children.map((child) => (
            <Render key={child.getIdentifier()} node={child as JCRNodeWrapper} view="card" />
          ))}
        </div>
      </div>
    );
  },
);
