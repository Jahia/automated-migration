import { jahiaComponent } from "@jahia/javascript-modules-library";

/**
 * Passthrough view (QUALITY-PLAN P1.2): renders the captured source markup
 * VERBATIM. This is the nothing-is-dropped half of the fidelity invariant —
 * every main-region area no semantic component covers is one of these nodes.
 * Asset URLs inside the markup are rewritten to the module's static/ mirror
 * copy at extraction time (extract_content assetBase), so the markup renders
 * offline-faithful under the source stylesheets loaded by the Layout.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "$NS:rawHtml",
    name: "default",
    displayName: "Raw HTML (passthrough)",
  },
  ({ html }: { html?: string }) => (
    // display:contents — the wrapper must be layout-transparent so grid/flex
    // relationships between sibling source regions survive
    // eslint-disable-next-line react/no-danger -- passthrough is the point
    <div
      data-passthrough="1"
      style={{ display: "contents" }}
      dangerouslySetInnerHTML={{ __html: html ?? "" }}
    />
  ),
);
