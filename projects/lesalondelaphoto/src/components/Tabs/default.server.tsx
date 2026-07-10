import { getChildNodes, jahiaComponent, Render, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

function resolveHeading(child: JCRNodeWrapper): string {
  try {
    if (child.hasProperty("heading")) {
      return child.getProperty("heading").getString();
    }
  } catch {
    // no heading
  }
  return child.getName();
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:tabs",
    displayName: "Tabs",
  },
  (_props: Record<string, unknown>, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();
    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:editorialBlock"),
    );

    if (isEdit) {
      return (
        <div className="component tabs col-12">
          <div className="component-content">
            <div style={{ display: "grid", gap: "8px" }}>
              {children.map((child) => (
                <div key={child.getIdentifier()} style={{ border: "1px solid #ccc", padding: "12px" }}>
                  <Render node={child as JCRNodeWrapper} view="default" readOnly />
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="component tabs col-12">
        <div className="component-content">
          <div className="tabs-container">
            <div className="tabs-nav" role="tablist">
              {children.map((child, idx) => (
                <button
                  key={child.getIdentifier()}
                  className={`tabs-tab ${idx === 0 ? "active" : ""}`}
                  role="tab"
                  aria-selected={idx === 0}
                >
                  <span>{resolveHeading(child)}</span>
                </button>
              ))}
            </div>
            <div className="tabs-panels">
              {children.map((child, idx) => (
                <div
                  key={child.getIdentifier()}
                  className={`tabs-panel ${idx === 0 ? "active" : ""}`}
                  role="tabpanel"
                  style={{ display: idx === 0 ? "block" : "none" }}
                >
                  <Render node={child as JCRNodeWrapper} view="default" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  },
);
