import { jahiaComponent, Render, useServerContext } from "@jahia/javascript-modules-library";
import { createElement, type ReactNode } from "react";
import { splitRoot, rootProps } from "../rawRoot.js";
import {
  childNodesOf,
  chunkTopLevel,
  composeNode,
  nodePayload,
  sanitizeFragment,
  substitutePayload,
} from "../skeletonRender.js";

/**
 * Passthrough view (QUALITY-PLAN P1.2): renders the captured source markup
 * VERBATIM. This is the nothing-is-dropped half of the fidelity invariant —
 * every main-region area no semantic component covers is one of these nodes.
 * P2.5: a demoted block with liftable text carries a `skeleton` + body*
 * richtext props instead of `html` — same markup, editable text runs.
 *
 * P6.3-bis: a rawHtml CONTAINER whose skeleton carries {{child:N}} markers can
 * hold TYPED library children ($NS:carousel/tabs/logoWall). In EDIT/PREVIEW those
 * children must render through Jahia's pipeline (<Render node/>) so each gets its
 * own Page-Builder EDIT FRAME (rule 28 / G6b) — string composition alone leaves
 * them un-clickable. LIVE keeps the byte-exact string composition (composeNode).
 * Same edit-mode interleaving as the skeleton section views.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "$NS:rawHtml",
    name: "default",
    displayName: "Raw HTML (passthrough)",
  },
  (props: Record<string, unknown>) => {
    const { currentNode, renderContext } = useServerContext();
    const node = currentNode as never;
    let editMode = false;
    try {
      editMode = (renderContext as { isEditMode: () => boolean }).isEditMode();
    } catch {
      editMode = false;
    }

    // ── EDIT/PREVIEW: interleave <Render> per {{child:N}} so typed children
    //    (library containers/atoms) are reachable edit frames (rule 28 / G6b) ──
    if (editMode && typeof props.skeleton === "string" && props.skeleton) {
      const p = nodePayload(node);
      const html = substitutePayload(p).replace(/\{\{(?:f|media|link):[^}]+\}\}/g, "");
      if (html.includes("{{child:")) {
        const kids = childNodesOf(node);
        const placed = new Set<number>();
        // SINGLE-PASS (no deep recursion): chunk the skeleton ONCE at the top
        // level. A top-level {{child:N}} marker renders its child via <Render>
        // (its own edit frame). A chunk that still holds a nested marker renders
        // as static HTML (markers stripped); its children are appended below via
        // the missed-children fallback so they still get frames (edit-mode visual
        // position is NOT the fidelity contract; LIVE is). Recursing into large
        // marker-bearing fragments was O(n^2) and timed out on whole-page
        // containers (200KB skeleton, 60s render cap) — this is O(n).
        const body = chunkTopLevel(html).map((c, i) => {
          if (c.kind === "child") {
            placed.add(c.idx);
            const kid = kids[c.idx];
            return createElement(
              "div",
              { key: `c${i}`, style: { display: "contents" } },
              kid ? createElement(Render as never, { node: kid }) : null,
            );
          }
          return createElement("div", {
            key: `h${i}`,
            style: { display: "contents" },
            dangerouslySetInnerHTML: { __html: c.html.replace(/\{\{child:\d+\}\}/g, "") },
          });
        });
        // reachability guarantee (G6): every child NOT placed at the top level
        // (nested inside a chunk) is rendered through the pipeline here so it
        // always gets an edit frame.
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
    }

    // ── LIVE (and no-child skeleton / verbatim): byte-exact string composition ──
    let html = typeof props.html === "string" ? props.html : "";
    if (typeof props.skeleton === "string" && props.skeleton) {
      html = composeNode(node);
    } else {
      html = sanitizeFragment(html);
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
