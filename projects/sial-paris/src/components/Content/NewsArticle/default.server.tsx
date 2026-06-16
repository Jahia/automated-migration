import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:newsArticle",
    displayName: "News Article Card",
  },
  (props: Props, { currentNode }) => {
    const { category, publishDate, title, excerpt, thumbnail } = props;

    return (
      <article className="news-card">
        {thumbnail && (
          <div className="news-card__thumbnail">
            <img
              src={buildNodeUrl(thumbnail)}
              alt={title ?? ""}
              className="news-card__image"
              loading="lazy"
            />
          </div>
        )}
        <div className="news-card__body">
          <div className="news-card__meta">
            {category && <span className="news-card__category">{category}</span>}
            {publishDate && (
              <time dateTime={publishDate} className="news-card__date">
                {new Date(publishDate).toLocaleDateString("en", { dateStyle: "medium" })}
              </time>
            )}
          </div>
          {title && (
            <h3 className="news-card__title">
              <a href={buildNodeUrl(currentNode)} className="news-card__link">
                {title}
              </a>
            </h3>
          )}
          {excerpt && <p className="news-card__excerpt">{excerpt}</p>}
        </div>
      </article>
    );
  },
);
