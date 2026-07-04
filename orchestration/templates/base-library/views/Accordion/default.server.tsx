import { jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
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
  ({ heading }: { heading?: string }) => (
    <section className={styles.root}>
      {heading && <h2 className={styles.heading}>{heading}</h2>}
      <div className={styles.container}>
        <RenderChildren filter="$NS:faqItem" />
      </div>
    </section>
  ),
);
