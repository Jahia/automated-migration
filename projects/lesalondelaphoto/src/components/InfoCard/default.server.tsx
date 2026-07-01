import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { InfoCardProps } from "./types.js";

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
    nodeType: "lsp:infoCard",
    displayName: "Info Card",
  },
  ({ image, imageAltText, titre, description }: InfoCardProps) => {
    const imageUrl = resolveImageUrl(image);

    return (
      <div className="component item-content-popin-picture col-12">
        <div className="component-content">
          <div className="info-card">
            {imageUrl && (
              <div className="info-card-icon">
                <img
                  src={imageUrl}
                  alt={imageAltText || titre || "Icon"}
                  loading="lazy"
                  style={{ maxHeight: "64px", maxWidth: "64px" }}
                />
              </div>
            )}
            {titre && <h3 className="field-titre info-card-title">{titre}</h3>}
            {description && (
              <div className="field-description info-card-desc" dangerouslySetInnerHTML={{ __html: description }} />
            )}
          </div>
        </div>
      </div>
    );
  },
);
