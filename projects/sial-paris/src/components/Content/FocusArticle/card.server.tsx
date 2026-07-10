import { buildModuleFileUrl, buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import { useTranslation } from "react-i18next";
import type { Props } from "./types.js";
import classes from "./focusCard.module.css";

/**
 * Focus Article card — horizontal layout matching the reference focus listing:
 * image (left) + title + excerpt + "Découvrir" CTA (right), stacked single-column.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:focusArticle",
    name: "card",
    displayName: "Focus Article Card (horizontal)",
  },
  ({ excerpt, thumbnail, "jcr:title": title }: Props, { currentNode }) => {
    const { t } = useTranslation();
    const url = buildNodeUrl(currentNode);
    const thumbnailUrl = thumbnail
      ? buildNodeUrl(thumbnail)
      : buildModuleFileUrl("static/assets/images/news-1.jpg");

    return (
      <article className={classes.card}>
        <a href={url} className={classes.imageCol} tabIndex={-1} aria-hidden="true">
          <img className={classes.image} src={thumbnailUrl} alt="" loading="lazy" />
        </a>
        <div className={classes.content}>
          {title && (
            <h3 className={classes.title}>
              <a href={url} className={classes.titleLink}>{title}</a>
            </h3>
          )}
          {excerpt && <p className={classes.excerpt}>{excerpt}</p>}
          <a href={url} className={classes.cta}>
            <span>{t("focus.discover")}</span>
          </a>
        </div>
      </article>
    );
  },
);
