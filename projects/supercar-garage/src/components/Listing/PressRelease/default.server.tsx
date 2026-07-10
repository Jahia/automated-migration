import {
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { useTranslation } from "react-i18next";
import type { PressReleaseProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:pressRelease",
    displayName: "Press Release",
  },
  (
    { "jcr:title": title, publishDate, image, summary, pressContact }: PressReleaseProps,
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const { t } = useTranslation();
    const cardUrl = buildNodeUrl(currentNode);
    const imageSrc = image ? buildNodeUrl(image) : undefined;

    let formattedDate: string | undefined;
    if (publishDate) {
      try {
        formattedDate = new Date(publishDate).toLocaleDateString(undefined, {
          year: "numeric",
          month: "long",
          day: "numeric",
        });
      } catch (_) {
        formattedDate = publishDate;
      }
    }

    return (
      <article className="search-result-item">
        <a href={cardUrl} className="search-result-link">
          <div className="labels">
            {imageSrc && (
              <img
                src={imageSrc}
                alt={title ?? ""}
                loading="lazy"
              />
            )}
            <div>
              <span className="label-type">
                {t("pressRelease.badge")}
              </span>
            </div>
          </div>

          {formattedDate && (
            <time className="text-muted" dateTime={publishDate}>
              {formattedDate}
            </time>
          )}

          {title && (
            <h3 className="field-title">{title}</h3>
          )}

          {summary && (
            <div
              className="field-description"
              dangerouslySetInnerHTML={{ __html: summary }}
            />
          )}

          {pressContact && (
            <p className="h3">{pressContact}</p>
          )}
        </a>
      </article>
    );
  },
);
