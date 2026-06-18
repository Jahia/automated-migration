import { RenderChildren, jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:featureItem", displayName: "Feature Item" },
  (props: Props) => {
    const { iconClass, heading, description } = props;
    return (
      <div className="col-md-4 feature-item">
        <div className="feature-card">
          {iconClass && <div className="feature-icon"><i className={iconClass}></i></div>}
          {heading && <h3 className="feature-heading">{heading}</h3>}
          {description && <p className="feature-description">{description}</p>}
        </div>
      </div>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:featureList",
    displayName: "Feature List",
  },
  (props: Props) => {
    const { overline, heading } = props;
    return (
      <section className="component feature-list container-bp col-12">
        <div className="component-content">
          {overline && <div className="focus-title">{overline}</div>}
          {heading && <h2 className="field-titre">{heading}</h2>}
          <div className="row wrapper">
            <RenderChildren />
          </div>
        </div>
      </section>
    );
  },
);
