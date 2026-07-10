import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ImgContentBlockProps } from "./types.js";

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
    nodeType: "usg:imgContentBlock",
    displayName: "Image Content Block",
  },
  (props: ImgContentBlockProps, { currentNode }) => {
    const { iconClass, image, heading, body, ctaLabel } = props;

    const linkHref = resolveLinkHref(currentNode as unknown as JCRNodeWrapper);
    const showCta = ctaLabel && linkHref !== "#";
    const imageSrc = image ? buildNodeUrl(image) : undefined;

    return (
      <div className="component content img-content-block-l mb-50 col-12">
        <div className="component-content">
          <div className="div1 bg-gray-1" />
          <div className="container-bp ">
            <div className="row ">
              {imageSrc && (
                <div className="col-md-6 pr-md-0">
                  <img
                    src={imageSrc}
                    alt={heading ?? ""}
                    className="basic-radius"
                    loading="lazy"
                  />
                </div>
              )}
              <div className="col-md-6 align-self-center bg-gray-1 mx-15-sm">
                <div className="simple-title col-12">
                  <div className="focus-title" />
                </div>
                <div className="row ">
                  {iconClass && (
                    <div className="col-md-2">
                      <div className="icon">
                        <i className={`${iconClass} fa-3x`} />
                      </div>
                    </div>
                  )}
                  <div className={iconClass ? "col-md-10" : "col-md-12"}>
                    {heading && (
                      <h2 className="field-title">{heading}</h2>
                    )}
                    {body && (
                      <div
                        className="rich-text field-description"
                        dangerouslySetInnerHTML={{ __html: body }}
                      />
                    )}
                    {showCta && (
                      <div className="btn btn-solid-primary mt-30 field-cta">
                        <a href={linkHref}>{ctaLabel}</a>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  },
);
