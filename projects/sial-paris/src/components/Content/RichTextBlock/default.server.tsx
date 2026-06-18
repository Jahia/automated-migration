import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:richTextBlock",
    displayName: "Rich Text Block",
  },
  (props: Props) => {
    const { overline, heading, body } = props;
    return (
      <section className="component rich-text-block container-bp col-12">
        <div className="component-content">
          {overline && <div className="focus-title">{overline}</div>}
          {heading && <h2 className="field-titre">{heading}</h2>}
          {body && <div className="rich-text-body" dangerouslySetInnerHTML={{ __html: body }} />}
        </div>
      </section>
    );
  },
);
