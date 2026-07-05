import { Render, useServerContext } from "@jahia/javascript-modules-library";
import { createElement, type ReactNode } from "react";
import { splitRoot, rootProps } from "./rawRoot.js";
import {
  composeNode,
  nodePayload,
  substitutePayload,
  childNodesOf,
  chunkTopLevel,
} from "./skeletonRender.js";

/**
 * useSkeleton — the SKELETON-FIRST branch every library view opens with.
 *
 * A MIGRATED node carries its captured source markup in `skeleton`
 * ({{f:*}}/{{media:*}}/{{link:href}}/{{child:N}} markers lifted by the zone
 * bridge, self-checked byte-exact at emission). Rendering such a node through
 * the library's own markup would break the fidelity contract, so when the
 * prop is present the view composes the skeleton instead. Editor-authored
 * nodes (no skeleton) return null here and fall through to the library
 * rendering.
 *
 * LIVE: composeNode() — string composition, byte-identical to the captured
 * source when unedited (the ground-truth invariant). Child nodes splice into
 * {{child:N}} recursively (containers) or via their verbatim `html` (rawHtml).
 *
 * EDIT/PREVIEW: children render through Jahia's pipeline (<Render node/>) so
 * each gets its own Page Builder edit frame (G6b) — including any child the
 * recursive placement missed (reachability guarantee).
 */
export function useSkeleton(): ReactNode | null {
  const { currentNode, renderContext } = useServerContext();
  const node = currentNode as never as Parameters<typeof nodePayload>[0];
  const p = nodePayload(node);
  if (!p.skeleton) return null;

  let editMode = false;
  try {
    editMode = (renderContext as unknown as { isEditMode: () => boolean }).isEditMode();
  } catch {
    editMode = false;
  }

  if (editMode) {
    const html = substitutePayload(p).replace(/\{\{(?:f|media|link):[^}]+\}\}/g, "");
    if (html.includes("{{child:")) {
      const kids = childNodesOf(node);
      const placed = new Set<number>();
      const compose = (fragment: string): ReactNode[] =>
        chunkTopLevel(fragment).map((c, i) => {
          if (c.kind === "child") {
            placed.add(c.idx);
            const kid = kids[c.idx];
            return createElement(
              "div",
              { key: `c${i}`, style: { display: "contents" } },
              kid ? createElement(Render as never, { node: kid }) : null,
            );
          }
          if (c.html.includes("{{child:")) {
            const root = splitRoot(c.html);
            if (root) {
              return createElement(
                root.tag,
                { ...rootProps(root.attrs), key: `e${i}` },
                compose(root.inner),
              );
            }
            // marker-bearing but not single-root: recurse on the raw fragment
            // so deeply/awkwardly nested {{child}} still resolve
            return createElement(
              "div",
              { key: `w${i}`, style: { display: "contents" } },
              compose(c.html),
            );
          }
          return createElement("div", {
            key: `h${i}`,
            style: { display: "contents" },
            dangerouslySetInnerHTML: { __html: c.html },
          });
        });
      const body = compose(html);
      // reachability guarantee (G6): any item the recursive placement missed
      // still renders through the pipeline so editors can always reach it
      const missed = kids
        .map((k, i) => [k, i] as const)
        .filter(([, i]) => !placed.has(i));
      return createElement(
        "div",
        { style: { display: "contents" } },
        body,
        missed.map(([k, i]) => createElement(Render as never, { key: `m${i}`, node: k })),
      );
    }
    // no items: fall through to the exact composition (still selectable — the
    // node itself is rendered through the pipeline by its Area)
  }

  const html = composeNode(node);
  // render the fragment's REAL root element — child/sibling CSS selectors
  // (section spacing rules) must keep matching (display:contents does not
  // participate in selector matching)
  const root = splitRoot(html);
  if (root) {
    return createElement(root.tag, {
      ...rootProps(root.attrs),
      dangerouslySetInnerHTML: { __html: root.inner },
    });
  }
  return createElement("div", {
    style: { display: "contents" },
    dangerouslySetInnerHTML: { __html: html },
  });
}
