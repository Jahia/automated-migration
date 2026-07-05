import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { resolveImageUrl } from "../lib.js";
import { Verbatim } from "../Verbatim.js";
import { useSkeleton } from "../SkeletonBody.js";
import styles from "./iconWithText.module.css";

/**
 * $NS:iconWithText — an icon + rich label row (generalized from jahiacom-v3
 * iconWithText, whose label is the ONE richtext field in that repo).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:iconWithText", displayName: "Icon With Text" },
  (props: { icon?: JCRNodeWrapper; iconAlt?: string; label?: string; skeletonOrig?: string }) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;

    const iconSrc = resolveImageUrl(props.icon);
    if (!iconSrc && !props.label) return <Verbatim html={props.skeletonOrig} />;

    return (
      <div className={styles.root}>
        {iconSrc && <img className={styles.icon} src={iconSrc} alt={props.iconAlt ?? ""} loading="lazy" />}
        {props.label && (
          <div
            className={styles.label}
            // eslint-disable-next-line react/no-danger -- CMS rich-text output
            dangerouslySetInnerHTML={{ __html: props.label }}
          />
        )}
      </div>
    );
  },
);
