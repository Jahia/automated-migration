import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:newsArticle",
    displayName: "News Article Full Page",
    name: "fullPage",
  },
  (props: Props, { currentNode }) => {
    const { category, publishDate, title, excerpt, body, thumbnail } = props;

    return (
      <main className="article-page">
        <div className="container">
          <article className="article-full">
            {thumbnail && (
              <div className="article-full__hero">
                <img
                  src={buildNodeUrl(thumbnail)}
                  alt={title ?? ""}
                  className="article-full__hero-image"
                />
              </div>
            )}
            <header className="article-full__header">
              {category && <span className="article-full__category">{category}</span>}
              {publishDate && (
                <time dateTime={publishDate} className="article-full__date">
                  {new Date(publishDate).toLocaleDateString("en", { dateStyle: "long" })}
                </time>
              )}
              {title && <h1 className="article-full__title">{title}</h1>}
              {excerpt && <p className="article-full__excerpt">{excerpt}</p>}
            </header>
            {body && (
              <div
                className="article-full__body richtext"
                dangerouslySetInnerHTML={{ __html: body }}
              />
            )}
          </article>
        </div>
      </main>
    );
  },
);
