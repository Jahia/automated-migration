import { getChildNodes, jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Verbatim } from "../Verbatim.js";
import { useSkeleton } from "../SkeletonBody.js";
import styles from "./accordion.module.css";

/**
 * $NS:accordion — Q/A rows (generalized from lsp:accordion / jahiacom-v3
 * faqSection). `+ * ($NS:faqItem)`: the editor adds N rows. RenderChildren
 * renders each faqItem (native <details>) through the pipeline and injects the
 * Add affordance in edit mode (G6b). Works identically in edit and live — the
 * faqItem is a self-contained <details> so no edit-mode branch is needed.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:accordion", displayName: "Accordion" },
  (
    { heading, skeletonOrig }: { heading?: string; skeletonOrig?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;

    // No editorial rows and no heading → verbatim backstop instead of an empty shell.
    const rows = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("$NS:faqItem"),
    );
    if (rows.length === 0 && !heading) return <Verbatim html={skeletonOrig} />;

    return (
      <section className={styles.root}>
        {heading && <h2 className={styles.heading}>{heading}</h2>}
        <div className={styles.container}>
          <RenderChildren filter="$NS:faqItem" />
        </div>
      </section>
    );
  },
);
