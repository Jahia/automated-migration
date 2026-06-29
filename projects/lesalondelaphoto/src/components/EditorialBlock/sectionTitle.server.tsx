import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { EditorialBlockProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:editorialBlock",
    name: "sectionTitle",
    displayName: "Section Title",
  },
  ({ heading }: EditorialBlockProps) => {
    return (
      <div className="component simple-title mb-50 mt-50 col-12">
        <div className="component-content">
          <div className="focus-title" />
          {heading && <h2 className="field-titre">{heading}</h2>}
        </div>
      </div>
    );
  },
);
