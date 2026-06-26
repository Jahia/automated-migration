import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

/**
 * Home page template — no banner/breadcrumb (the home leads with the hero
 * carousel). Shared top-bar, navigation and footer come from Layout's
 * AbsoluteAreas; the home's hero + content sections live in the editable
 * "main" area.
 */
jahiaComponent(
  {
    componentType: "template",
    nodeType: "jnt:page",
    name: "home",
    displayName: "Home page",
  },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    <Layout title={title ?? ""}>
      <Area name="main" />
    </Layout>
  ),
);
