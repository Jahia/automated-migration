import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { EditorialBlockProps } from "./types.js";

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
    nodeType: "usg:editorialBlock",
    displayName: "Editorial Block (Image left)",
  },
  (props: EditorialBlockProps, { currentNode }) => {
    const { heading, subheading, image, body, ctaLabel } = props;

    const linkHref = resolveLinkHref(currentNode as unknown as JCRNodeWrapper);
    const showCta = ctaLabel && linkHref !== "#";
    const imageSrc = image ? buildNodeUrl(image) : undefined;

    return (
      <div className="component content-block left-img col-12">
        <div className="component-content">
          <div className="container-bp">
            <div className="row align-items-center">
              {imageSrc && (
                <div className="col-md-6">
                  <img
                    src={imageSrc}
                    alt={heading ?? ""}
                    sizes="655px"
                    className="img-cover "
                    loading="lazy"
                  />
                </div>
              )}
              <div className={imageSrc ? "col-md-6 pl-md-40" : "col-md-12"}>
                {heading && (
                  <h2 className="title-n3 mb-20 pt-sm-50  field-title">{heading}</h2>
                )}
                {subheading && (
                  <div className="subheading field-subheading">{subheading}</div>
                )}
                {body && (
                  <div
                    className="pb-sm-20 field-description"
                    dangerouslySetInnerHTML={{ __html: body }}
                  />
                )}
                {showCta && (
                  <div className="btn btn-solid-primary mt-50 field-contentblockcta">
                    <a href={linkHref}>{ctaLabel}</a>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  },
);
