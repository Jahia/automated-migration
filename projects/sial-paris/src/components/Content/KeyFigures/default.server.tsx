import {
  getChildNodes,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:keyFigures",
    displayName: "Key Figures",
  },
  (_props: Props, { currentNode }) => {
    const figures = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("sialp:keyFigure"),
    );

    return (
      <section className="component key-figures container bg-gray-1 animated-key-figures col-12">
        <div className="component-content">
          <div className="simple-title col-12">
            <div className="focus-title">SIAL en bref</div>
            <h2 className="field-titre">Les chiffres clés</h2>
          </div>
          <div className="container-bp">
            <div className="row wrapper">
              {figures.map((fig: JCRNodeWrapper) => {
                const icon = fig.hasProperty("icon") ? fig.getPropertyAsString("icon") : "fa-solid fa-circle";
                const number = fig.hasProperty("number") ? fig.getPropertyAsString("number") : "";
                const unit = fig.hasProperty("unit") ? fig.getPropertyAsString("unit") : "";
                const label = fig.hasProperty("label") ? fig.getPropertyAsString("label") : "";
                return (
                  <div key={fig.getPath()} className="col">
                    <div>
                      <i className={icon}></i>
                      <div className="figure-number">
                        <span className="field-chiffre-N">{number}{unit ? ` ${unit}` : ""}</span>
                        <div className="field-description-N">{label}</div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>
    );
  },
);
