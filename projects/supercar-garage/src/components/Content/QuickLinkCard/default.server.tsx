import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { QuickLinkCardProps } from "./types.js";

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
    nodeType: "usg:quickLinkCard",
    displayName: "Quick Link Card",
  },
  (props: QuickLinkCardProps, { currentNode }) => {
    const { iconClass, heading } = props;
    const jcrNode = currentNode as unknown as JCRNodeWrapper;
    const href = resolveLinkHref(jcrNode);
    const isExternal = jcrNode.hasProperty("j:linkType") &&
      jcrNode.getProperty("j:linkType").getString() === "external";

    if (href === "#") return null;

    return (
      <a
        href={href}
        {...(isExternal
          ? { target: "_blank", rel: "noopener noreferrer nofollow" }
          : {})}
      >
        <div>
          <div>
            <div>
              {iconClass && <i className={iconClass}></i>}
            </div>
          </div>
          {heading && <h3 className="field-titre">{heading}</h3>}
        </div>
      </a>
    );
  },
);
