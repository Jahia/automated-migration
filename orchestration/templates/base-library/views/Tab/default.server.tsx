import { jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import styles from "./tab.module.css";

/**
 * $NS:tab — one titled pane holding an OPEN palette of atoms. Title via
 * jcr:title (mix:title supertype); used by the parent $NS:tabs as the tab label.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:tab", displayName: "Tab" },
  () => (
    <div className={styles.tab}>
      <RenderChildren />
    </div>
  ),
);
