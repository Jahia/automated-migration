import { Area, jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import { Layout, type Shell } from "../Layout.jsx";

jahiaComponent(
  {
    componentType: "template",
    nodeType: "jnt:page",
    name: "basic",
    displayName: "Basic page",
  },
  ({ "jcr:title": title }: { "jcr:title": string }) => {
    const { currentNode } = useServerContext();
    // Per-page SHELL spec installed by load_content (source body attrs +
    // ancestor chain + chrome/scripts around <main>) — see Layout.
    let shell: Shell | null = null;
    try {
      if (currentNode.hasNode("shell")) {
        shell = JSON.parse(
          currentNode.getNode("shell").getProperty("html").getString(),
        ) as Shell;
      }
    } catch {
      shell = null; // malformed/absent spec: plain layout fallback
    }
    return (
      <Layout title={title} shell={shell}>
        <Area name="main" />
      </Layout>
    );
  },
);
