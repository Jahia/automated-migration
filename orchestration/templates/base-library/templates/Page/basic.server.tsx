import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

/**
 * Basic (inner) page template — ONE open composition surface, the deployed
 * lesalondelaphoto "structured by components only" pattern: the contributor
 * builds the page from the palette, no fixed slots. Children-only atoms are
 * excluded (they belong inside their containers). $NS:rawHtml stays droppable
 * as the fidelity safety net.
 */
const OPEN_PALETTE = [
  "$NS:section",
  "$NS:gridRow",
  "$NS:cardGrid",
  "$NS:logoWall",
  "$NS:carousel",
  "$NS:tabs",
  "$NS:accordion",
  "$NS:jcrQuery",
  "$NS:richText",
  "$NS:heading",
  "$NS:image",
  "$NS:iconWithText",
  "$NS:divider",
  "$NS:rawHtml",
];

jahiaComponent(
  { componentType: "template", nodeType: "jnt:page", name: "basic", displayName: "Basic page" },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    <Layout title={title || ""}>
      <Area name="main" allowedNodeTypes={OPEN_PALETTE} />
    </Layout>
  ),
);
