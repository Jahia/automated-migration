import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { HeroProps } from "./types.js";

function resolveImageUrl(image: JCRNodeWrapper | undefined): string | undefined {
  if (!image) return undefined;
  try {
    return buildNodeUrl(image);
  } catch {
    return undefined;
  }
}

function resolveCta(node: HeroProps, current: JCRNodeWrapper): { url?: string; label?: string } {
  const linkType = node["j:linkType"];
  if (!linkType || linkType === "none") return {};
  const label = node.ctaLabel || undefined;
  if (linkType === "internal") {
    try {
      if (current.hasProperty("j:linknode")) {
        const linked = current.getProperty("j:linknode").getNode() as JCRNodeWrapper;
        return { url: buildNodeUrl(linked), label };
      }
    } catch {
      // no internal link
    }
  } else if (linkType === "external") {
    try {
      if (current.hasProperty("j:url")) {
        return { url: current.getProperty("j:url").getString(), label };
      }
    } catch {
      // no external url
    }
  }
  return {};
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:hero",
    name: "default",
    displayName: "Hero Banner",
  },
  (node: HeroProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const heading = node.heading;
    const subheading = node.subheading;
    const imageUrl = resolveImageUrl(node.image);
    const altText = node.imageAltText || "";
    const cta = resolveCta(node, currentNode);

    return (
      <div className="component Slide">
        <div className="component-content">
          {imageUrl && (
            <img src={imageUrl} alt={altText} className="slide-img" loading="eager" />
          )}
          <div>
            {heading && <h2 className="field-slidesmalltitle">{heading}</h2>}
            {subheading && <h3 className="field-description field-slidetext">{subheading}</h3>}
            {cta.url && cta.label && (
              <a href={cta.url} className="btn btn-solid-primary mr-20">
                <span>{cta.label}</span>
              </a>
            )}
          </div>
        </div>
      </div>
    );
  },
);
