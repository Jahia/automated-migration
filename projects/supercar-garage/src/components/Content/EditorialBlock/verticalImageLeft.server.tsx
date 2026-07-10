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
    displayName: "Editorial Block (Vertical image left)",
    name: "verticalImageLeft",
  },
  (props: EditorialBlockProps, { currentNode }) => {
    const { heading, subheading, image, body, ctaLabel } = props;

    const linkHref = resolveLinkHref(currentNode as unknown as JCRNodeWrapper);
    const showCta = ctaLabel && linkHref !== "#";
    const imageSrc = image ? buildNodeUrl(image) : undefined;
    const isExternal = currentNode.hasProperty("j:linkType") &&
      (currentNode as unknown as JCRNodeWrapper).getProperty("j:linkType").getString() === "external";

    return (
      <div className="component content-block-vertical-image left-img col-12">
        <div className="component-content">
          <div className="container-bp">
            <div className="row justify-content-between ">
              {imageSrc && (
                <div className="col-md-5 col-lg-4">
                  <img
                    src={imageSrc}
                    alt={heading ?? ""}
                    sizes="480px"
                    className="img-cover"
                    loading="lazy"
                  />
                </div>
              )}
              <div className="col-md-7  align-self-center">
                <div />
                {heading && (
                  <h2 className="title-n3 mb-20 pt-sm-50  field-title">{heading}</h2>
                )}
                {subheading && (
                  <div className="subheading field-subheading">{subheading}</div>
                )}
                {body && (
                  <div
                    className="pb-sm-20 rich-text field-description"
                    dangerouslySetInnerHTML={{ __html: body }}
                  />
                )}
                {showCta && (
                  <div className="button">
                    <a
                      href={linkHref}
                      className="btn btn-primary mt-30"
                      {...(isExternal ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                    >
                      <span>{ctaLabel}</span>
                    </a>
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
