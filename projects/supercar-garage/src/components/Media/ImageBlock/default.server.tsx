import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { ImageBlockProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:imageBlock",
    displayName: "Image Block",
  },
  ({ image, alt }: ImageBlockProps) => (
    <div className="component image-de-fond background-img">
      <div className="component-content">
        {image && (
          <img src={buildNodeUrl(image)} alt={alt ?? ""} />
        )}
      </div>
    </div>
  ),
);
