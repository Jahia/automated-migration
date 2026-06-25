import {
  AddResources,
  buildModuleFileUrl,
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { PartnersCarouselProps } from "./types.js";
import styles from "./component.module.css";

/**
 * Safely resolve the href for a partnerLogo child node.
 * Reads j:linkType, j:linknode, j:url directly from the child node.
 */
function resolveLogoHref(child: JCRNodeWrapper): string | undefined {
  try {
    if (!child.hasProperty("j:linkType")) return undefined;
    const linkType = child.getProperty("j:linkType").getString();
    if (linkType === "internal" && child.hasProperty("j:linknode")) {
      const ref = child.getProperty("j:linknode").getNode() as JCRNodeWrapper;
      return buildNodeUrl(ref);
    }
    if (linkType === "external" && child.hasProperty("j:url")) {
      return child.getProperty("j:url").getString();
    }
  } catch (_) {}
  return undefined;
}

/**
 * Safely read a string property from a JCR node.
 */
function getProp(node: JCRNodeWrapper, name: string): string {
  try {
    if (node.hasProperty(name)) {
      return node.getProperty(name).getString() ?? "";
    }
  } catch (_) {}
  return "";
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:partnersCarousel",
    displayName: "Partners Carousel",
  },
  (
    { heading }: PartnersCarouselProps,
    {
      currentNode,
      renderContext,
    }: {
      currentNode: JCRNodeWrapper;
      renderContext: import("org.jahia.services.render").RenderContext;
    },
  ) => {
    const isEdit = renderContext.isEditMode();

    const children = getChildNodes(
      currentNode,
      -1,
      0,
      (n: JCRNodeWrapper) => n.isNodeType("usg:partnerLogo"),
    );

    const items = children.map((child: JCRNodeWrapper) => {
      const href = resolveLogoHref(child);
      const altText = getProp(child, "altText");
      let imageSrc: string | undefined;
      try {
        if (child.hasProperty("image")) {
          const imgNode = child.getProperty("image").getNode() as JCRNodeWrapper;
          imageSrc = buildNodeUrl(imgNode);
        }
      } catch (_) {}
      return { key: child.getIdentifier(), href, altText, imageSrc };
    });

    if (isEdit) {
      // In edit mode render flat so editors can click individual logos
      return (
        <div className="component partners-carrousel col-12">
          <div className="component-content">
            {heading && <h2 className={styles.heading}>{heading}</h2>}
            <div className={styles.editGrid}>
              {items.map(({ key, href, altText, imageSrc }) =>
                imageSrc ? (
                  href ? (
                    <a key={key} href={href} className="content col-4 col-md-3">
                      <img src={imageSrc} alt={altText || ""} loading="lazy" />
                    </a>
                  ) : (
                    <span key={key} className="content col-4 col-md-3">
                      <img src={imageSrc} alt={altText || ""} loading="lazy" />
                    </span>
                  )
                ) : null,
              )}
            </div>
          </div>
        </div>
      );
    }

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
                <li className="row slide-visible" style={{ margin: 0 }}>
                  {items.map(({ key, href, altText, imageSrc }) =>
                    imageSrc ? (
                      href ? (
                        <a
                          key={key}
                          href={href}
                          className="content col-4 col-md-3"
                          target="_blank"
                          rel="nofollow noopener noreferrer"
                        >
                          <img
                            src={imageSrc}
                            alt={altText || ""}
                            loading="lazy"
                          />
                        </a>
                      ) : (
                        <span key={key} className="content col-4 col-md-3">
                          <img
                            src={imageSrc}
                            alt={altText || ""}
                            loading="lazy"
                          />
                        </span>
                      )
                    ) : null,
                  )}
                </li>
              </ul>
            </div>
          </div>
        </div>
      </>
    );
  },
);
