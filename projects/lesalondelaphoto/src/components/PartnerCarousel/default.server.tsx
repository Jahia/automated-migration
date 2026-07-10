import { getChildNodes, jahiaComponent, Render, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { PartnerCarouselProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:partnerCarousel",
    displayName: "Partner Carousel",
  },
  ({ heading }: PartnerCarouselProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();
    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:partnerItem"),
    );

    if (isEdit) {
      return (
        <div className="component partners-carrousel col-12">
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
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                gap: "16px",
              }}
            >
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
      <div className="component partners-carrousel col-12">
        <div className="component-content">
          {heading && (
            <div className="component simple-title mb-50 mt-50 col-12">
              <div className="component-content">
                <div className="focus-title" />
                <h2 className="field-titre">{heading}</h2>
              </div>
            </div>
          )}
          <div className="swiffy-slider slider-nav-page slider-indicators-outside slider-indicators-dark slider-nav-animation slider-nav-animation-fadein slider-item-first-visible slider-item-show4"
            data-slider-nav-autoplay="true"
            data-slider-nav-autoplay-interval="3500"
          >
            <ul className="slider-container" style={{ display: "flex", padding: 0 }}>
              {children.map((child) => (
                <Render key={child.getIdentifier()} node={child as JCRNodeWrapper} view="default" />
              ))}
            </ul>
            <button type="button" className="slider-nav" aria-label="Go to previous" />
            <button type="button" className="slider-nav slider-nav-next" aria-label="Go to next" />
            <div className="slider-indicators">
              {children.map((child, idx) => (
                <button
                  key={child.getIdentifier()}
                  className={idx === 0 ? "active" : ""}
                  aria-label={`Go to slide ${idx + 1}`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  },
);
