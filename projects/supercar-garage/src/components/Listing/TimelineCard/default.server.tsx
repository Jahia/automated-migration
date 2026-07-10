import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { TimelineCardProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:timelineCard",
    displayName: "Timeline Card",
  },
  ({ heading, description }: TimelineCardProps) => (
    <div className="col-md-6 col-lg-4 card">
      {heading && <h3 className="field-titre">{heading}</h3>}
      {description && (
        <div
          className="field-description"
          dangerouslySetInnerHTML={{ __html: description }}
        />
      )}
    </div>
  ),
);
