import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { InfoCardProps } from "./types.js";

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
    nodeType: "usg:infoCard",
    displayName: "Info Card",
  },
  (
    { iconClass, heading, body, ctaLabel }: InfoCardProps,
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const linkHref = resolveLinkHref(currentNode);
    const hasLink = linkHref !== "#" && ctaLabel;

    return (
      <div className="col-md-4">
        <div className="d-flex">
          <div className="card-body">
            {heading && <h2 className="field-titre">{heading}</h2>}
            {body && (
              <div
                className="field-description"
                dangerouslySetInnerHTML={{ __html: body }}
              />
            )}
            {hasLink && (
              <a href={linkHref} className="btn btn-primary">
                <span>{ctaLabel}</span>
              </a>
            )}
          </div>
          <div className="icon">
            <i className={iconClass ?? ""} />
          </div>
        </div>
      </div>
    );
  },
);
