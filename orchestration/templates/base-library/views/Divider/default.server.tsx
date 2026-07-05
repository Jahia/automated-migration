import { jahiaComponent } from "@jahia/javascript-modules-library";
import styles from "./divider.module.css";
import { useSkeleton } from "../SkeletonBody.js";

/**
 * $NS:divider — a visual separator (rule / blank space) atom.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:divider", displayName: "Divider" },
  (props: { style?: string }) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;

    if (props.style === "space") return <div className={styles.space} aria-hidden="true" />;
    return <hr className={styles.line} />;
  },
);
