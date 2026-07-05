import { jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { resolveCtaUrl } from "../lib.js";
import styles from "./button.module.css";

/**
 * $NS:button — the primary CTA atom (generalized from lsp:ctaButton).
 * Link via j:linkType; label via ctaLabel; style axes via theme + isSmall/mainCTA.
 * All props optional at runtime (CLAUDE.md rule 5).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:button", displayName: "CTA Button" },
  (
    props: {
      ctaLabel?: string;
      "j:linkType"?: string;
      theme?: string;
      isSmall?: boolean;
      mainCTA?: boolean;
    },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const { renderContext } = useServerContext();
    const label = props.ctaLabel;
    const url = resolveCtaUrl(props["j:linkType"], currentNode);

    // In edit mode, always render a placeholder so the empty atom is clickable.
    if (!url || !label) {
      return renderContext.isEditMode() ? (
        <span className={styles.placeholder}>{label || "CTA"}</span>
      ) : null;
    }

    const cls = [
      styles.btn,
      props.mainCTA ? styles.main : styles.secondary,
      props.isSmall ? styles.small : "",
      props.theme ? styles[`theme_${props.theme}`] : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <a href={url} className={cls}>
        <span>{label}</span>
      </a>
    );
  },
);
