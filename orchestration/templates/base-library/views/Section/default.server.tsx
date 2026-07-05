import { jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
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
  (props: { heading?: string; bgColor?: string; spacing?: string }) => {
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
