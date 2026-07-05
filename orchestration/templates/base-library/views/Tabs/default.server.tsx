import {
  getChildNodes,
  jahiaComponent,
  Render,
  RenderChildren,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { getProp } from "../lib.js";
import { Verbatim } from "../Verbatim.js";
import { TabsIsland } from "./TabsIsland.client.js";
import styles from "./tabs.module.css";

/**
 * $NS:tabs — a tabbed container of $NS:tab panes (P6.3-bis: promoted from a JS tabs
 * widget — ARIA tablist or AEM cmp-tabs). EDIT mode: stacked panes, each a
 * clickable edit frame (RenderChildren) so every tab is reachable in Page Builder
 * (G6b). LIVE mode: a CLIENT ISLAND (TabsIsland) re-hydrates click-to-show on the
 * composable pane children; the tab label comes from each pane's jcr:title. The
 * first pane is visible before hydration (progressive enhancement).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:tabs", displayName: "Tabs" },
  (
    {
      heading,
      skeleton,
      skeletonOrig,
    }: { heading?: string; skeleton?: string; skeletonOrig?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const { renderContext } = useServerContext();

    const panes = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("$NS:tab"),
    );

    // No editorial panes → verbatim backstop instead of an empty tabs shell.
    if (panes.length === 0) return <Verbatim html={skeleton ?? skeletonOrig} />;

    if (renderContext.isEditMode()) {
      return (
        <div className={styles.root}>
          {heading && <h2 className={styles.heading}>{heading}</h2>}
          <div className={styles.editStack}>
            <RenderChildren filter="$NS:tab" />
          </div>
        </div>
      );
    }
    const labels = panes.map(
      (pane) => getProp(pane as JCRNodeWrapper, "jcr:title") || pane.getName(),
    );

    return (
      <TabsIsland heading={heading} labels={labels}>
        {panes.map((pane) => (
          <Render key={pane.getIdentifier()} node={pane as JCRNodeWrapper} />
        ))}
      </TabsIsland>
    );
  },
);
