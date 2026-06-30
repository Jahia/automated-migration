import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

// Page-droppable content components (extend lspmix:pageComponent). The hero area is
// restricted to the landing hero/carousel; the main area to body content components.
// Children (ctaButton/socialLink/footerLink/slide), shell types (mainNav/footer →
// AbsoluteArea) and mainResource detail types (newsArticle/agendaItem → folder
// content listed via jcrQuery) are intentionally NOT droppable here.
const HERO_TYPES = ["lsp:hero", "lsp:heroCarousel"];
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
    name: "home",
    displayName: "Home page",
  },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    // Layout already provides <main>; do not nest another <main>.
    <Layout title={title || ""}>
      <Area name="hero" allowedNodeTypes={HERO_TYPES} />
      <Area name="main" allowedNodeTypes={MAIN_TYPES} />
    </Layout>
  ),
);
