import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { CtaButtonProps } from "./types.js";

function resolveCtaUrl(linkType: string | undefined, current: JCRNodeWrapper): string | undefined {
  if (!linkType || linkType === "none") return undefined;
  if (linkType === "internal") {
    try {
      if (current.hasProperty("j:linknode")) {
        return buildNodeUrl(current.getProperty("j:linknode").getNode() as JCRNodeWrapper);
      }
    } catch {}
  } else if (linkType === "external") {
    try {
      if (current.hasProperty("j:url")) {
        return current.getProperty("j:url").getString();
      }
    } catch {}
  }
  return undefined;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:ctaButton",
    displayName: "CTA Button",
  },
  (node: CtaButtonProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const label = node.ctaLabel;
    const url = resolveCtaUrl(node["j:linkType"], currentNode);

    if (!url || !label) return null;

    return (
      <a href={url} className="btn btn-primary mt-30">
        <span>{label}</span>
      </a>
    );
  },
);
