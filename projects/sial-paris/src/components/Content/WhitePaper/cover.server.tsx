import { buildModuleFileUrl, buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import { useTranslation } from "react-i18next";
import type { Props } from "./types.js";
import classes from "./whitePaperCard.module.css";

/**
 * White Paper card — image cover with title + excerpt overlaid at the bottom,
 * matching the reference Livres-blancs listing (3-up grid). Clicking the card
 * downloads the attached PDF when present, otherwise opens the white-paper page.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:whitePaper",
    name: "cover",
    displayName: "White Paper Cover Card",
  },
  ({ excerpt, thumbnail, document, "jcr:title": title }: Props, { currentNode }) => {
    const { t } = useTranslation();
    const pageUrl = buildNodeUrl(currentNode);
    const href = document ? buildNodeUrl(document) : pageUrl;
    const isDownload = Boolean(document);
    const thumbnailUrl = thumbnail
      ? buildNodeUrl(thumbnail)
      : buildModuleFileUrl("static/assets/images/news-1.jpg");

    return (
      <a
        href={href}
        className={classes.card}
        {...(isDownload ? { download: true } : {})}
        aria-label={title}
      >
        <img className={classes.image} src={thumbnailUrl} alt="" loading="lazy" />
        <div className={classes.overlay}>
          {title && <h3 className={classes.title}>{title}</h3>}
          {excerpt && <p className={classes.excerpt}>{excerpt}</p>}
          <span className={classes.cta}>{t("whitePaper.download")}</span>
        </div>
      </a>
    );
  },
);
