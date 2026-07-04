import { jahiaComponent, RenderChild } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { resolveImageUrl } from "../lib.js";
import styles from "./card.module.css";

/**
 * $NS:card — the richest ATOM. Node-level lifted fields: jcr:title, body, image,
 * imageAltText, theme, cornerCut = 6 (< K=8). The `tag` and `button` are fixed
 * CHILD nodes rendered through the Jahia pipeline (RenderChild → clickable edit
 * frames in Page Builder, contribution rule 28 / G6b). Variants are style-mixin
 * choices (theme / cornerCut), NOT hash-suffixed types (migration.md rule 21).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:card", displayName: "Card" },
  (props: {
    "jcr:title"?: string;
    body?: string;
    image?: JCRNodeWrapper;
    imageAltText?: string;
    theme?: string;
    cornerCut?: string;
  }) => {
    const title = props["jcr:title"];
    const imgSrc = resolveImageUrl(props.image);

    const cls = [
      styles.card,
      props.theme ? styles[`theme_${props.theme}`] : "",
      props.cornerCut && props.cornerCut !== "none" ? styles[props.cornerCut] : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <article className={cls}>
        {imgSrc && (
          <div className={styles.media}>
            <img src={imgSrc} alt={props.imageAltText ?? ""} loading="lazy" />
          </div>
        )}
        <div className={styles.body}>
          {/* tag: a fixed child slot; RenderChild shows an Add button when empty in edit mode */}
          <RenderChild name="tag" />
          {title && <h3 className={styles.title}>{title}</h3>}
          {props.body && (
            <div
              className={styles.text}
              // eslint-disable-next-line react/no-danger -- CMS rich-text output
              dangerouslySetInnerHTML={{ __html: props.body }}
            />
          )}
          {/* button: a fixed child slot rendered through the pipeline */}
          <RenderChild name="button" />
        </div>
      </article>
    );
  },
);
