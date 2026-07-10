import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { SectionTitleProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:sectionTitle",
    displayName: "Section Title",
  },
  ({ heading }: SectionTitleProps) => (
    <div className="component simple-title mb-50 mt-50 col-12">
      <div className="component-content">
        <div className="focus-title" />
        {heading && <h2 className="field-titre">{heading}</h2>}
      </div>
    </div>
  ),
);
