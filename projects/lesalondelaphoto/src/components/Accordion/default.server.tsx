import { getChildNodes, jahiaComponent, Render, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { AccordionProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:accordion",
    displayName: "Accordion",
  },
  ({ heading }: AccordionProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();
    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:accordionItem"),
    );

    if (isEdit) {
      return (
        <div className="component accordion col-12">
          <div className="component-content">
            {heading && (
              <div className="component simple-title mb-50 mt-50 col-12">
                <div className="component-content">
                  <div className="focus-title" />
                  <h2 className="field-titre">{heading}</h2>
                </div>
              </div>
            )}
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
      <div className="component accordion col-12">
        <div className="component-content">
          {heading && (
            <div className="component simple-title mb-50 mt-50 col-12">
              <div className="component-content">
                <div className="focus-title" />
                <h2 className="field-titre">{heading}</h2>
              </div>
            </div>
          )}
          <div className="accordion-container">
            {children.map((child) => (
              <Render key={child.getIdentifier()} node={child as JCRNodeWrapper} view="default" />
            ))}
          </div>
        </div>
      </div>
    );
  },
);
