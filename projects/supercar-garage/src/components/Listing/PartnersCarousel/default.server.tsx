import {
  AddResources,
  buildModuleFileUrl,
  jahiaComponent,
  RenderChildren,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { PartnersCarouselProps } from "./types.js";
import styles from "./component.module.css";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:partnersCarousel",
    displayName: "Partners Carousel",
  },
  (
    { heading }: PartnersCarouselProps,
    {
      renderContext,
    }: {
      renderContext: import("org.jahia.services.render").RenderContext;
    },
  ) => {
    const isEdit = renderContext.isEditMode();

    if (isEdit) {
      // In edit mode render flat so editors can click individual logos
      return (
        <div className="component partners-carrousel col-12">
          <div className="component-content">
            {heading && <h2 className={styles.heading}>{heading}</h2>}
            <div className={styles.editGrid}>
              <RenderChildren filter="usg:partnerLogo" />
            </div>
          </div>
        </div>
      );
    }

    // Live mode: each usg:partnerLogo view emits its own <li> inside the slider <ul>
    return (
      <>
        <AddResources
          type="javascript"
          resources={buildModuleFileUrl("static/js/swiffy-slider.min.js")}
        />
        <div className="component partners-carrousel col-12">
          <div className="component-content">
            {heading && <h2 className={styles.heading}>{heading}</h2>}
            <div className="swiffy-slider slider-nav-page slider-indicators-outside slider-indicators-dark slider-nav-animation slider-nav-animation-fadein slider-item-first-visible">
              <ul className="slider-container">
                <RenderChildren filter="usg:partnerLogo" />
              </ul>
            </div>
          </div>
        </div>
      </>
    );
  },
);
