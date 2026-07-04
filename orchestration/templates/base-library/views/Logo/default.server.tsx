import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { resolveCtaUrl, resolveImageUrl } from "../lib.js";
import styles from "./logo.module.css";

/**
 * $NS:logo — a single logo image + optional link (the discoverasr brand-logo
 * atom, DECOMP-PROTOTYPE §4). Image via $NSMIX:media, link via $NSMIX:cta.
 * This is the atom a $NS:logoWall repeats.
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:logo", displayName: "Logo" },
  (
    props: { image?: JCRNodeWrapper; imageAltText?: string; "j:linkType"?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const src = resolveImageUrl(props.image);
    if (!src) return null;
    const alt = props.imageAltText ?? "";
    const url = resolveCtaUrl(props["j:linkType"], currentNode);

    const img = <img className={styles.logo} src={src} alt={alt} loading="lazy" />;

    return url ? (
      <a href={url} className={styles.link} aria-label={alt || undefined}>
        {img}
      </a>
    ) : (
      <span className={styles.link}>{img}</span>
    );
  },
);
