import { jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { resolveCtaUrl } from "../lib.js";
import { Verbatim } from "../Verbatim.js";
import { useSkeleton } from "../SkeletonBody.js";
import styles from "./chevronLink.module.css";

/**
 * $NS:chevronLink — arrow/chevron text link (generalized from jahiacom-v3
 * chevronButton). Label + j:linkType via $NSMIX:cta.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:chevronLink", displayName: "Chevron Link" },
  (
    props: { ctaLabel?: string; "j:linkType"?: string; skeletonOrig?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;

    const { renderContext } = useServerContext();
    const label = props.ctaLabel;
    const url = resolveCtaUrl(props["j:linkType"], currentNode);

    if (!url || !label) {
      if (props.skeletonOrig) return <Verbatim html={props.skeletonOrig} />;
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
