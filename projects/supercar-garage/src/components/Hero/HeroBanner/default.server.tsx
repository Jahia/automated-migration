import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { HeroBannerProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:heroBanner",
    displayName: "Hero Banner",
  },
  ({ heading, backgroundImage }: HeroBannerProps) => (
    <div className="component title banner-title container  text-center text-white col-12">
      <div className="component-content">
        <div className="fields-container">
          <h1 className="field-titre">{heading}</h1>
        </div>
        {backgroundImage && (
          <img
            src={buildNodeUrl(backgroundImage)}
            alt={heading ?? ""}
            rel="preload"
            fetchPriority="high"
          />
        )}
      </div>
    </div>
  ),
);
