import { Area, jahiaComponent } from "@jahia/javascript-modules-library";
import { Layout } from "../Layout.js";

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jnt:page",
    name: "basic",
    displayName: "Basic page",
  },
  ({ "jcr:title": title }) => (
    <Layout title={title}>
      <Area name="main" />
    </Layout>
  ),
);
