import {
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { useTranslation } from "react-i18next";
import type { NewsArticleProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:newsArticle",
    displayName: "News Article",
  },
  (
    { "jcr:title": title, publishDate, image, summary, author }: NewsArticleProps,
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

    let tags: string[] = [];
    try {
      if (currentNode.hasProperty("j:tagList")) {
        const tagValues = currentNode.getProperty("j:tagList").getValues();
        for (let i = 0; i < tagValues.length; i++) {
          tags.push(tagValues[i].getString());
        }
      }
    } catch (_) {}

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
                {t("newsArticle.badge")}
              </span>
              {tags.map((tag) => (
                <span key={tag} className="label-theme">
                  {tag}
                </span>
              ))}
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

          {author && (
            <p className="text-muted">{author}</p>
          )}
        </a>
      </article>
    );
  },
);
