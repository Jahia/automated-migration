import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

// Standard section page: an OPEN composition surface — gridRow (layout) + body content
// components. "Structured by components only": the contributor builds the page from the
// palette; no fixed slots. Children/shell/mainResource types stay excluded.
const OPEN_PALETTE = [
  "lsp:gridRow",
  "lsp:editorialBlock",
  "lsp:cardGrid",
  "lsp:promoBlock",
  "lsp:partnerCarousel",
  "lsp:jcrQuery",
  "lsp:externalEmbed",
];

jahiaComponent(
  { componentType: "template", nodeType: "jnt:page", name: "basic", displayName: "Basic page" },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    <Layout title={title || ""}>
      <Area name="main" allowedNodeTypes={OPEN_PALETTE} />
    </Layout>
  ),
);
