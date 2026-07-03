import { jahiaComponent } from "@jahia/javascript-modules-library";
import { createElement } from "react";
import { splitRoot, rootProps } from "../rawRoot.js";

/**
 * Passthrough view (QUALITY-PLAN P1.2): renders the captured source markup
 * VERBATIM. This is the nothing-is-dropped half of the fidelity invariant —
 * every main-region area no semantic component covers is one of these nodes.
 * The fragment's REAL root element is rendered natively (child/sibling CSS
 * selectors keep matching); multi-root fragments fall back to a
 * display:contents wrapper.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "$NS:rawHtml",
    name: "default",
    displayName: "Raw HTML (passthrough)",
  },
  ({ html }: { html?: string }) => {
    const root = splitRoot(html ?? "");
    if (root) {
      return createElement(root.tag, {
        ...rootProps(root.attrs),
        "data-passthrough": "1",
        dangerouslySetInnerHTML: { __html: root.inner },
      });
    }
    return (
      // eslint-disable-next-line react/no-danger -- passthrough is the point
      <div
        data-passthrough="1"
        style={{ display: "contents" }}
        dangerouslySetInnerHTML={{ __html: html ?? "" }}
      />
    );
  },
);
