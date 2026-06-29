import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { HeroProps } from "./types.js";

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
    name: "compact",
    displayName: "Hero Compact",
  },
  (node: HeroProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const heading = node.heading;
    const cta = resolveCta(node, currentNode);

    return (
      <div className="compact-hero">
        {cta.url ? (
          <a href={cta.url}>
            <div className="compact-hero-icon">
              <div>
                <i className="fa-solid fa-arrow-right" />
              </div>
            </div>
          </a>
        ) : null}
        {heading && <h3 className="field-titre">{heading}</h3>}
      </div>
    );
  },
);
