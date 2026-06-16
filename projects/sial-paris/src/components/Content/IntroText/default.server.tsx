import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:introText",
    displayName: "Intro Text",
  },
  ({ overline, heading, body }: Props) => (
    <div className="component rich-text col-12 bg-secondary">
      <div className="component-content">
        <div className="container-bp p-20 mb-20 field-description">
          {overline && <p>{overline}</p>}
          {heading && <h2 className="title-n2">{heading}</h2>}
          {body && <div dangerouslySetInnerHTML={{ __html: body ?? "" }} />}
        </div>
      </div>
    </div>
  ),
);
