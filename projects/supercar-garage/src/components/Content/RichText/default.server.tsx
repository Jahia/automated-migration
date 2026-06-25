import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { RichTextProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:richText",
    displayName: "Rich Text",
  },
  ({ heading, body }: RichTextProps) => {
    if (!heading && !body) return null;

    return (
      <div className="component rich-text col-12">
        <div className="component-content">
          <div className="container-bp p-20 mb-20 field-description">
            {heading && <h2 className="title-n2">{heading}</h2>}
            {body && (
              // eslint-disable-next-line react/no-danger
              <div dangerouslySetInnerHTML={{ __html: body }} />
            )}
          </div>
        </div>
      </div>
    );
  },
);
