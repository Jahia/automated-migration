import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { PlainHtmlProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:plainHtml",
    displayName: "Plain HTML",
  },
  ({ htmlContent }: PlainHtmlProps) => {
    if (!htmlContent) {
      return null;
    }

    return (
      <div
        className="component plain-html"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: htmlContent }}
      />
    );
  },
);
