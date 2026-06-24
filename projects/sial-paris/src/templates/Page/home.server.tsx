import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jnt:page",
    name: "home",
    displayName: "Home page",
  },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => (
    <Layout title={title}>
      <main className="home-main">
        <Area name="hero" />
        <Area name="main" />
      </main>
    </Layout>
  ),
);
