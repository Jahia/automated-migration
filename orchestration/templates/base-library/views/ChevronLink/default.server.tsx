import { jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { resolveCtaUrl } from "../lib.js";
import styles from "./chevronLink.module.css";

/**
 * $NS:chevronLink — arrow/chevron text link (generalized from jahiacom-v3
 * chevronButton). Label + j:linkType via $NSMIX:cta.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:chevronLink", displayName: "Chevron Link" },
  (
    props: { ctaLabel?: string; "j:linkType"?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const { renderContext } = useServerContext();
    const label = props.ctaLabel;
    const url = resolveCtaUrl(props["j:linkType"], currentNode);

    if (!url || !label) {
      return renderContext.isEditMode() ? (
        <span className={styles.placeholder}>{label || "Link"}</span>
      ) : null;
    }

    return (
      <a href={url} className={styles.chevron}>
        <span>{label}</span>
        <span className={styles.arrow} aria-hidden="true">
          &rsaquo;
        </span>
      </a>
    );
  },
);
