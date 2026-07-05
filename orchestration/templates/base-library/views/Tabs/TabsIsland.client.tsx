"use client";

import { Children, type ReactNode, useState } from "react";
import styles from "./tabs.module.css";

/**
 * TabsIsland — the CLIENT island that re-hydrates click-to-show on a tabs widget
 * whose panes are now COMPOSABLE child nodes (P6.3-bis, promoted from a JS tabs
 * widget: ARIA tablist or AEM cmp-tabs). It WRAPS the server-rendered pane children
 * (each a real Jahia-pipeline node → its own Page-Builder edit frame in EDIT, G6b),
 * toggling which pane is visible on tab click. First tab active by default; ARIA
 * tablist semantics. Replaces the source site's bespoke tabs JS.
 */
export function TabsIsland({
  heading,
  labels,
  children,
}: {
  heading?: string;
  labels: string[];
  children: ReactNode;
}) {
  const panes = Children.toArray(children);
  const [active, setActive] = useState(0);

  return (
    <div className={styles.root}>
      {heading && <h2 className={styles.heading}>{heading}</h2>}
      <div className={styles.nav} role="tablist">
        {panes.map((_, i) => (
          <button
            key={i}
            type="button"
            className={`${styles.tab} ${i === active ? styles.active : ""}`}
            role="tab"
            aria-selected={i === active}
            onClick={() => setActive(i)}
          >
            <span>{labels[i] || `Tab ${i + 1}`}</span>
          </button>
        ))}
      </div>
      <div className={styles.panels}>
        {panes.map((pane, i) => (
          <div
            key={i}
            className={styles.panel}
            role="tabpanel"
            aria-hidden={i !== active}
            style={{ display: i === active ? "block" : "none" }}
          >
            {pane}
          </div>
        ))}
      </div>
    </div>
  );
}
