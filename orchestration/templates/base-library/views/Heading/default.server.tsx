import { jahiaComponent } from "@jahia/javascript-modules-library";
import { createElement } from "react";
import styles from "./heading.module.css";

/**
 * $NS:heading — a section title atom (generalized from jahiacom-v3 titleSection).
 * Title comes from jcr:title (mix:title supertype — never a bespoke `title` prop).
 * `level` chooses the semantic tag; `subtitle` is optional supporting text.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:heading", displayName: "Heading" },
  (props: { "jcr:title"?: string; subtitle?: string; level?: string }) => {
    const title = props["jcr:title"];
    const level = props.level && ["h2", "h3", "h4"].includes(props.level) ? props.level : "h2";

    if (!title && !props.subtitle) return null;

    return (
      <div className={styles.root}>
        {title && createElement(level, { className: styles.title }, title)}
        {props.subtitle && <p className={styles.subtitle}>{props.subtitle}</p>}
      </div>
    );
  },
);
