import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.js";

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jmix:mainResource",
    name: "default",
    displayName: "Main Resource Page",
  },
  (_: Record<string, unknown>, { currentNode }: { currentNode: JCRNodeWrapper }) => (
    <Layout title={currentNode.getDisplayableName()}>
      <Render node={currentNode} view="fullPage" />
    </Layout>
  ),
);
