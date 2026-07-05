import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { resolveImageUrl } from "../lib.js";
import styles from "./tag.module.css";

/**
 * $NS:tag — a tag/badge chip (generalized from jahiacom-v3 tagItem).
 * Label + style via $NSMIX:badge; optional small icon image.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:tag", displayName: "Tag / Badge" },
  (props: {
    badgeLabel?: string;
    badgeStyle?: string;
    tagImg?: JCRNodeWrapper;
    tagImgAlt?: string;
  }) => {
    const label = props.badgeLabel;
    const iconSrc = resolveImageUrl(props.tagImg);
    if (!label && !iconSrc) return null;

    const style = props.badgeStyle && ["info", "success", "warning"].includes(props.badgeStyle)
      ? props.badgeStyle
      : "default";

    return (
      <span className={`${styles.tag} ${styles[`style_${style}`]}`}>
        {iconSrc && <img className={styles.icon} src={iconSrc} alt={props.tagImgAlt ?? ""} />}
        {label && <span>{label}</span>}
      </span>
    );
  },
);
