import { getChildNodes, jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Verbatim } from "../Verbatim.js";
import { useSkeleton } from "../SkeletonBody.js";
import styles from "./section.module.css";

/**
 * $NS:section — an OPEN composition surface (generalized from jahiacom-v3
 * sectionCustom / lesalondelaphoto's open Areas). `+ * ($NSMIX:component)`:
 * the editor adds/reorders/removes ANY atom. RenderChildren renders every child
 * through the Jahia pipeline AND auto-injects the "Add Content" button in edit
 * mode (contribution rule 28 / gate G6b) — this is what makes the block
 * composable in Page Builder.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:section", displayName: "Section" },
  (
    props: { heading?: string; bgColor?: string; spacing?: string; skeletonOrig?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;

    // No editorial children and no heading → verbatim backstop instead of an empty
    // <section> shell (G1: 0 empty shells).
    const kids = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("$NSMIX:component"),
    );
    if (kids.length === 0 && !props.heading) return <Verbatim html={props.skeletonOrig} />;

    const cls = [
      styles.section,
      props.bgColor ? styles[props.bgColor.replace("-", "_")] : "",
      props.spacing ? styles[`sp_${props.spacing}`] : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <section className={cls}>
        <div className={styles.inner}>
          {props.heading && <h2 className={styles.heading}>{props.heading}</h2>}
          <RenderChildren />
        </div>
      </section>
    );
  },
);
