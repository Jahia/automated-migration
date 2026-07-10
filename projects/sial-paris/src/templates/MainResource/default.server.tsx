import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.js";

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jmix:mainResource",
    priority: -1,
  },
  ({ "jcr:title": title }: { "jcr:title"?: string }, { currentNode }) => (
    <Layout title={title}>
      <main>
        <Render node={currentNode as JCRNodeWrapper} view="fullPage" />
      </main>
    </Layout>
  ),
);
