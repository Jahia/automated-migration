import { jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import type { TimelineCardsProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:timelineCards",
    displayName: "Timeline Cards",
  },
  ({ heading }: TimelineCardsProps) => (
    <div className="col-12">
      {heading && (
        <div className="component simple-title mb-50 mt-50 col-12">
          <div className="component-content">
            <div className="focus-title" />
            <h2 className="field-titre">{heading}</h2>
          </div>
        </div>
      )}
      <div className="component item-list container-bp col-12">
        <div className="component-content">
          <RenderChildren />
        </div>
      </div>
    </div>
  ),
);
