import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { SocialLinkProps } from "./types.js";

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
    nodeType: "usg:socialLink",
    displayName: "Social Link",
  },
  (props: SocialLinkProps, { currentNode }) => {
    const href = resolveLinkHref(currentNode as JCRNodeWrapper);
    const iconClass = props.iconClass;
    const platform = props.platform;

    if (!iconClass) return null;

    return (
      <a
        target="_blank"
        rel="noopener noreferrer nofollow"
        href={href !== "#" ? href : undefined}
        aria-label={platform ?? iconClass}
      >
        <div>
          <i className={iconClass} aria-hidden="true" />
        </div>
      </a>
    );
  },
);
