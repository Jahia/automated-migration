import { getChildNodes, jahiaComponent, Render, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:anchorsLinks",
    displayName: "Anchors Links",
  },
  (_props: Record<string, unknown>, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();
    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:ctaButton"),
    );

    if (isEdit) {
      return (
        <div className="component anchors-links col-12">
          <div className="component-content">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "8px" }}>
              {children.map((child) => (
                <div key={child.getIdentifier()} style={{ border: "1px solid #ccc", padding: "8px" }}>
                  <Render node={child as JCRNodeWrapper} view="default" readOnly />
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="component anchors-links col-12">
        <div className="component-content">
          <div className="anchors-links-bar" style={{ display: "flex", flexWrap: "wrap", gap: "12px", justifyContent: "center", padding: "16px 0" }}>
            {children.map((child) => (
              <Render key={child.getIdentifier()} node={child as JCRNodeWrapper} view="default" />
            ))}
          </div>
        </div>
      </div>
    );
  },
);
