import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { PartnerLogoProps } from "./types.js";

function resolveLinkHref(node: JCRNodeWrapper): string {
  if (!node.hasProperty("j:linkType")) return "#";
  const type = node.getProperty("j:linkType").getString();
  if (type === "internal" && node.hasProperty("j:linknode")) {
    try {
      return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
    } catch (_) {
      return "#";
    }
  }
  if (type === "external" && node.hasProperty("j:url")) {
    return node.getProperty("j:url").getString() ?? "#";
  }
  return "#";
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:partnerLogo",
    displayName: "Partner Logo",
  },
  (
    { image, altText }: PartnerLogoProps,
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    if (!image) return null;

    const linkHref = resolveLinkHref(currentNode);
    const isExternal =
      currentNode.hasProperty("j:linkType") &&
      currentNode.getProperty("j:linkType").getString() === "external";
    const imageUrl = buildNodeUrl(image);
    const resolvedAlt = altText ?? "";

    return (
      <a
        href={linkHref !== "#" ? linkHref : undefined}
        className="content col-4 col-md-3"
        target={isExternal ? "_blank" : undefined}
        rel={isExternal ? "nofollow noopener noreferrer" : undefined}
      >
        <img
          src={imageUrl}
          alt={resolvedAlt}
          loading="lazy"
        />
      </a>
    );
  },
);
