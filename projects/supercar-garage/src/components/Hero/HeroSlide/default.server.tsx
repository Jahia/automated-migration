import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { HeroSlideProps } from "./types.js";

function resolveLinkHref(node: JCRNodeWrapper): string {
  if (!node.hasProperty("j:linkType")) return "#";
  const type = node.getProperty("j:linkType").getString();
  if (type === "internal" && node.hasProperty("j:linknode")) {
    return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
  }
  if (type === "external" && node.hasProperty("j:url")) {
    return node.getProperty("j:url").getString() ?? "#";
  }
  return "#";
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:heroSlide",
    displayName: "Hero Slide",
  },
  (props: HeroSlideProps, { currentNode }) => {
    const { image, smallTitle, body, ctaLabel } = props;

    const imageSrc = image ? buildNodeUrl(image) : undefined;
    const imageAlt = smallTitle ?? "";

    const linkHref = resolveLinkHref(currentNode as unknown as JCRNodeWrapper);
    const showCta = ctaLabel && linkHref !== "#";

    return (
      <div className="component Slide">
        <div className="component-content">
          {imageSrc && (
            <img
              src={imageSrc}
              alt={imageAlt}
              className="slide-img"
              rel="preload"
              fetchPriority="high"
            />
          )}
          <div>
            {smallTitle && (
              <h2 className="field-slidesmalltitle">{smallTitle}</h2>
            )}
            {body && (
              <div
                className="field-description field-slidetext"
                dangerouslySetInnerHTML={{ __html: body }}
              />
            )}
            {showCta && (
              <div className="btn btn-solid-primary mr-20 field-slide-link1">
                <a href={linkHref} rel="noopener noreferrer">
                  {ctaLabel}
                </a>
              </div>
            )}
          </div>
          {imageSrc && (
            <img
              src={imageSrc}
              alt={imageAlt}
              className="slide-img"
              aria-hidden="true"
            />
          )}
        </div>
      </div>
    );
  },
);
