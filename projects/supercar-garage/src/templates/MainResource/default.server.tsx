import { jahiaComponent, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.js";

/**
 * Full-page template for any jmix:mainResource content node (news articles,
 * press releases, etc.). When a detail content node is requested at its own
 * URL, Jahia renders it through this template, which wraps the node's
 * `fullPage` view in the shared site Layout (header + footer).
 *
 * Low priority lets specific type templates override if ever added.
 */
jahiaComponent(
  {
    componentType: "template",
    nodeType: "jmix:mainResource",
    priority: -1,
  },
  (_props, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    let title = "";
    try {
      if (currentNode.hasProperty("jcr:title")) {
        title = currentNode.getProperty("jcr:title").getString() ?? "";
      }
    } catch (_) {
      // title not set
    }
    if (!title) {
      title = currentNode.getName();
    }

    return (
      <Layout title={title}>
        <main>
          <Render node={currentNode} view="fullPage" />
        </main>
      </Layout>
    );
  },
);
