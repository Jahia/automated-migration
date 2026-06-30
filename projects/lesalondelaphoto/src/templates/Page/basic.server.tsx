import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

// Standard section/content page: a single main content area, restricted to body
// content components (no landing hero/carousel — that is the home template's role).
const MAIN_TYPES = [
  "lsp:editorialBlock",
  "lsp:cardGrid",
  "lsp:promoBlock",
  "lsp:partnerCarousel",
  "lsp:jcrQuery",
  "lsp:externalEmbed",
  "lsp:gridRow",
];

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jnt:page",
    name: "basic",
    displayName: "Basic page",
  },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    // Layout already provides <main>; do not nest another <main>.
    <Layout title={title || ""}>
      <Area name="main" allowedNodeTypes={MAIN_TYPES} />
    </Layout>
  ),
);
