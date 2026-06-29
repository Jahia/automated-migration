import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { EditorialBlockProps } from "./types.js";

function resolveImageUrl(image: JCRNodeWrapper | undefined): string | undefined {
  if (!image) return undefined;
  try {
    return buildNodeUrl(image);
  } catch {
    return undefined;
  }
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:editorialBlock",
    name: "default",
    displayName: "Editorial Block",
  },
  ({ heading, body, image, imageAltText, imagePosition }: EditorialBlockProps) => {
    const imageUrl = resolveImageUrl(image);
    const altText = imageAltText || "";
    const imgPos = imagePosition === "right" ? "img-right" : "img-left";
    const hasImage = Boolean(imageUrl);

    return (
      <div className={`component rich-text col-12 ${hasImage ? imgPos : ""}`}>
        <div className="component-content">
          {hasImage && (
            <div className="editorial-image">
              <img src={imageUrl} alt={altText} className="img-responsive" loading="lazy" />
            </div>
          )}
          <div className={`container-bp p-20 mb-20 field-description ${hasImage ? "editorial-text" : ""}`}>
            {heading && <h2 className="title-n2">{heading}</h2>}
            {body && <div dangerouslySetInnerHTML={{ __html: body }} />}
          </div>
        </div>
      </div>
    );
  },
);
