import {
  getChildNodes,
  jahiaComponent,
  Render,
  RenderChildren,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { getProp } from "../lib.js";
import styles from "./tabs.module.css";

/**
 * $NS:tabs — a tabbed container of $NS:tab panes (generalized from lsp:tabs /
 * the popularDestinationsTabs target). EDIT mode: stacked panes, each a clickable
 * edit frame (RenderChildren) so every tab is reachable in Page Builder (G6b).
 * LIVE mode: an ARIA tablist; the tab label comes from each pane's jcr:title.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:tabs", displayName: "Tabs" },
  (
    { heading }: { heading?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const { renderContext } = useServerContext();

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

    const panes = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("$NS:tab"),
    );

    return (
      <div className={styles.root}>
        {heading && <h2 className={styles.heading}>{heading}</h2>}
        <div className={styles.nav} role="tablist">
          {panes.map((pane, idx) => (
            <button
              key={pane.getIdentifier()}
              className={`${styles.tab} ${idx === 0 ? styles.active : ""}`}
              role="tab"
              aria-selected={idx === 0}
            >
              <span>{getProp(pane as JCRNodeWrapper, "jcr:title") || pane.getName()}</span>
            </button>
          ))}
        </div>
        <div className={styles.panels}>
          {panes.map((pane, idx) => (
            <div
              key={pane.getIdentifier()}
              className={`${styles.panel} ${idx === 0 ? styles.active : ""}`}
              role="tabpanel"
              style={{ display: idx === 0 ? "block" : "none" }}
            >
              <Render node={pane as JCRNodeWrapper} />
            </div>
          ))}
        </div>
      </div>
    );
  },
);
