import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:keyFigure", displayName: "Key Figure" },
  (props: Props) => {
    const { icon, number, unit, label } = props;
    return (
      <div className="col">
        <div>
          {icon && <i className={icon} />}
          <div className="figure-number">
            <span className="field-chiffre-N">
              {number}{unit ? ` ${unit}` : ""}
            </span>
            {label && <div className="field-description-N">{label}</div>}
          </div>
        </div>
      </div>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:keyFigures",
    displayName: "Key Figures",
  },
  (props: Props, { currentNode }) => {
    const { overline, heading } = props;
    return (
      <section className="component key-figures container bg-gray-1 animated-key-figures col-12">
        <div className="component-content">
          <div className="simple-title col-12">
            {overline && <div className="focus-title">{overline}</div>}
            {heading && <h2 className="field-titre">{heading}</h2>}
          </div>
          <div className="container-bp">
            <div className="row wrapper">
              <RenderChildren />
            </div>
          </div>
        </div>
      </section>
    );
  },
);
