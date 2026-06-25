import { jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import type { KeyFiguresProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:keyFigures",
    displayName: "Key Figures",
  },
  ({ heading, animated }: KeyFiguresProps) => {
    const animatedClass = animated === true ? "animated-key-figures" : "";

    return (
      <div className={`component key-figures container bg-gray-1 ${animatedClass} col-12`.trim()}>
        <div className="component-content">
          <div className="simple-title col-12">
            <div className="focus-title" />
          </div>
          {heading && <h2 className="field-titre">{heading}</h2>}
          <div className="container-bp">
            <div className="row wrapper">
              <RenderChildren />
            </div>
          </div>
        </div>
      </div>
    );
  },
);
