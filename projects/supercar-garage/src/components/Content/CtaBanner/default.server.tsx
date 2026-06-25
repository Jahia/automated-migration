import { buildNodeUrl, jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { CtaBannerProps } from "./types.js";

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
    nodeType: "usg:ctaBanner",
    displayName: "CTA Banner",
  },
  ({ ctaLabel }: CtaBannerProps) => {
    const { currentNode } = useServerContext();
    const linkHref = resolveLinkHref(currentNode as unknown as JCRNodeWrapper);

    if (!ctaLabel || linkHref === "#") return null;

    return (
      <div className="component link row justify-content-center col-12">
        <div className="component-content">
          <a href={linkHref} className="btn btn-primary m-20">
            <span>{ctaLabel}</span>
          </a>
        </div>
      </div>
    );
  },
);
