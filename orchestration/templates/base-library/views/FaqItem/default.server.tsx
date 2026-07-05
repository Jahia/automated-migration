import { jahiaComponent } from "@jahia/javascript-modules-library";
import { Verbatim } from "../Verbatim.js";
import { useSkeleton } from "../SkeletonBody.js";
import styles from "./faqItem.module.css";

/**
 * $NS:faqItem — one Q/A row (generalized from jahiacom-v3 faqItem).
 * Question via jcr:title (mix:title supertype); answer is richtext.
 * Uses native <details>/<summary> so it works without JS (a11y-friendly).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:faqItem", displayName: "FAQ Item" },
  (props: { "jcr:title"?: string; answer?: string; skeletonOrig?: string }) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;

    const question = props["jcr:title"];
    if (!question && !props.answer) return <Verbatim html={props.skeletonOrig} />;

    return (
      <details className={styles.item}>
        <summary className={styles.question}>{question || "Question"}</summary>
        {props.answer && (
          <div
            className={styles.answer}
            // eslint-disable-next-line react/no-danger -- CMS rich-text output
            dangerouslySetInnerHTML={{ __html: props.answer }}
          />
        )}
      </details>
    );
  },
);
