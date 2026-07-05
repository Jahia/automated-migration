import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { resolveCtaUrl, resolveImageUrl } from "../lib.js";
import styles from "./image.module.css";

/**
 * $NS:image — an image atom (generalized from jahiacom-v3 imageItem).
 * Image + alt via $NSMIX:media; optional link via $NSMIX:cta; optional caption.
 * Image is a DAM weakreference (migration.md rule 15) — never a URL string.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:image", displayName: "Image" },
  (
    props: {
      image?: JCRNodeWrapper;
      imageAltText?: string;
      caption?: string;
      "j:linkType"?: string;
    },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const src = resolveImageUrl(props.image);
    if (!src) return null;
    const alt = props.imageAltText ?? "";
    const url = resolveCtaUrl(props["j:linkType"], currentNode);

    const img = <img className={styles.img} src={src} alt={alt} loading="lazy" />;

    return (
      <figure className={styles.root}>
        {url ? (
          <a href={url} className={styles.link}>
            {img}
          </a>
        ) : (
          img
        )}
        {props.caption && <figcaption className={styles.caption}>{props.caption}</figcaption>}
      </figure>
    );
  },
);
