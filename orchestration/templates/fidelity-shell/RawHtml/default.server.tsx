import { jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import { createElement } from "react";
import { splitRoot, rootProps } from "../rawRoot.js";
import { composeNode } from "../skeletonRender.js";

/**
 * Passthrough view (QUALITY-PLAN P1.2): renders the captured source markup
 * VERBATIM. This is the nothing-is-dropped half of the fidelity invariant —
 * every main-region area no semantic component covers is one of these nodes.
 * P2.5: a demoted block with liftable text carries a `skeleton` + body*
 * richtext props instead of `html` — same markup, editable text runs.
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
  (props: Record<string, unknown>) => {
    const { currentNode } = useServerContext();
    let html = typeof props.html === "string" ? props.html : "";
    if (typeof props.skeleton === "string" && props.skeleton) {
      // lifted anonymous block: full composition (body*/media/link markers)
      html = composeNode(currentNode as never);
    }
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
