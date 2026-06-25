import { jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import type { QuickLinksProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:quickLinks",
    displayName: "Quick Links",
  },
  ({ backgroundColor }: QuickLinksProps) => {
    const bgClass = backgroundColor ?? "bg-gray-1";

    return (
      <div className={`component quicklinkssticky container ${bgClass} col-12`}>
        <div className="component-content">
          <div className="container-bp">
            <div className="row justify-content-center">
              <RenderChildren />
            </div>
          </div>
        </div>
      </div>
    );
  },
);
