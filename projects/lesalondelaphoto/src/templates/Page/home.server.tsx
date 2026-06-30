import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

// hero = a RESTRICTED slot (only the landing hero/carousel).
const HERO_TYPES = ["lsp:hero", "lsp:heroCarousel"];
// main = an OPEN composition surface: the gridRow layout primitive + all body content
// components. The contributor builds the layout freely with these — but children
// (cta/social/footerLink/slide), shell (nav/footer = Layout) and mainResource detail
// types are excluded. Add the recovered components (keyFigures, accordion, tabs,
// contactBlock, dateLieuHoraires, infoCard, imageBlock, anchorsLinks) here as they ship.
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
  { componentType: "template", nodeType: "jnt:page", name: "home", displayName: "Home page" },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    // Layout already provides <main>; do not nest another <main>.
    <Layout title={title || ""}>
      <Area name="hero" allowedNodeTypes={HERO_TYPES} />
      <Area name="main" allowedNodeTypes={OPEN_PALETTE} />
    </Layout>
  ),
);
