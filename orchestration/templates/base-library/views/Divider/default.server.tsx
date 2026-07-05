import { jahiaComponent } from "@jahia/javascript-modules-library";
import styles from "./divider.module.css";

/**
 * $NS:divider — a visual separator (rule / blank space) atom.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:divider", displayName: "Divider" },
  (props: { style?: string }) => {
    if (props.style === "space") return <div className={styles.space} aria-hidden="true" />;
    return <hr className={styles.line} />;
  },
);
