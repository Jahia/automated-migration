import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

/**
 * Home page template — zones with allowedNodeTypes whitelists (the DEPLOYED
 * lesalondelaphoto pattern: `allowedNodeTypes` const arrays, NOT jahiacom-v3's
 * `allowedTypes`). "Zone size" = the granularity of these Areas (MODULARITY-PLAN
 * Pillar 3): `main` is ONE OPEN composition surface the contributor fills from
 * the palette — that IS the composability Julian is asking for.
 *
 * $NS is stamped to the project prefix. $NS:rawHtml is included so the
 * fidelity-shell passthrough (the shrinking safety net) is still droppable.
 */

// A restricted zone: only landing hero/carousel blocks.
const HERO_TYPES = ["$NS:carousel", "$NS:section"];

// The open palette: containers + rich atoms an editor composes the page from.
// Children-only atoms ($NS:card, $NS:tag, $NS:tab, $NS:logo, $NS:faqItem,
// $NS:button) are intentionally EXCLUDED — they belong INSIDE their containers.
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
  { componentType: "template", nodeType: "jnt:page", name: "home", displayName: "Home page" },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    <Layout title={title || ""}>
      <Area name="hero" allowedNodeTypes={HERO_TYPES} />
      <Area name="main" allowedNodeTypes={OPEN_PALETTE} />
    </Layout>
  ),
);
