import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ImageBlockProps } from "./types.js";

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
    nodeType: "lsp:imageBlock",
    displayName: "Image Block",
  },
  ({ image, imageAltText, caption }: ImageBlockProps) => {
    const imageUrl = resolveImageUrl(image);
    if (!imageUrl) return null;

    return (
      <div className="component image col-12">
        <div className="component-content">
          <div className="container-bp">
            <img
              src={imageUrl}
              alt={imageAltText || ""}
              className="img-responsive"
            />
            {caption && (
              <div className="field-imagecaption image-caption">
                {caption}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  },
);
