import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { ImageBlockProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:imageBlock",
    name: "contentImage",
    displayName: "Image Block (Content)",
  },
  ({ image, alt }: ImageBlockProps) => (
    <div className="component image container-bp col-12">
      <div className="component-content">
        {image && (
          <div style={{ textAlign: "center" }}>
            <img
              src={buildNodeUrl(image)}
              alt={alt ?? ""}
              style={{ display: "initial" }}
              loading="lazy"
            />
          </div>
        )}
      </div>
    </div>
  ),
);
