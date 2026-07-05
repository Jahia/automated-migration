import { createElement, type ReactElement } from "react";
import { splitRoot, rootProps } from "./rawRoot.js";
import { sanitizeFragment } from "./skeletonRender.js";

/**
 * <Verbatim> — the universal fidelity backstop for every base-library view.
 * Renders captured source markup (the hidden `skeletonOrig` prop) byte-exact
 * when a node's typed fields are all empty, so a lean/broken node NEVER collapses
 * to an empty shell (G1: 0 empty shells). Reuses the exact fidelity-shell RawHtml
 * mechanism: sanitizeFragment → splitRoot (real root element restores child/
 * sibling CSS selectors) → dangerouslySetInnerHTML, with a display:contents
 * wrapper fallback for multi-root/text fragments. Returns null when html is
 * absent, so it is behavior-preserving for nodes that carry no skeletonOrig.
 */
export function Verbatim({ html }: { html?: string }): ReactElement | null {
  if (!html) return null;
  const safe = sanitizeFragment(html);
  const root = splitRoot(safe);
  if (root) {
    return createElement(root.tag, {
      ...rootProps(root.attrs),
      "data-skeleton-orig": "1",
      // eslint-disable-next-line react/no-danger -- verbatim captured markup (fidelity backstop)
      dangerouslySetInnerHTML: { __html: root.inner },
    });
  }
  return createElement("div", {
    "data-skeleton-orig": "1",
    style: { display: "contents" },
    // eslint-disable-next-line react/no-danger -- verbatim captured markup (fidelity backstop)
    dangerouslySetInnerHTML: { __html: safe },
  });
}
