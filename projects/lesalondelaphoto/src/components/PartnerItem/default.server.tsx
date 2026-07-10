import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { PartnerItemProps } from "./types.js";

function resolveLink(linkType: string | undefined, current: JCRNodeWrapper): string | undefined {
  if (!linkType || linkType === "none") return undefined;
  if (linkType === "internal") {
    try {
      if (current.hasProperty("j:linknode")) {
        const linked = current.getProperty("j:linknode").getNode() as JCRNodeWrapper;
        return buildNodeUrl(linked);
      }
    } catch {
      // no internal link
    }
  } else if (linkType === "external") {
    try {
      if (current.hasProperty("j:url")) {
        return current.getProperty("j:url").getString();
      }
    } catch {
      // no external url
    }
  }
  return undefined;
}

function resolveImageUrl(logo: JCRNodeWrapper | undefined): string | undefined {
  if (!logo) return undefined;
  try {
    return buildNodeUrl(logo);
  } catch {
    return undefined;
  }
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:partnerItem",
    displayName: "Partner Logo",
  },
  (node: PartnerItemProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const logoUrl = resolveImageUrl(node.logo);
    const altText = node.name || "Partner";
    const linkUrl = resolveLink(node["j:linkType"], currentNode);

    const imgEl = logoUrl ? (
      <img
        src={logoUrl}
        alt={altText}
        loading="lazy"
        style={{ maxHeight: "80px", maxWidth: "160px" }}
      />
    ) : null;

    return (
      <li className="slide-visible" style={{ margin: 0, listStyle: "none" }}>
        {linkUrl ? (
          <a href={linkUrl} className="content" target="_blank" rel="noopener noreferrer">
            {imgEl}
          </a>
        ) : (
          <div className="content">{imgEl}</div>
        )}
      </li>
    );
  },
);
