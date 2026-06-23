import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

function getCategoryLabels(node: JCRNodeWrapper): string[] {
  try {
    if (!node.hasProperty("j:defaultCategory")) return [];
    return node.getProperty("j:defaultCategory").getValues().map((v: any) => {
      try { return v.getNode().getDisplayableName(); } catch { return null; }
    }).filter(Boolean);
  } catch { return []; }
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:focusArticle",
    displayName: "Focus Article Card",
    name: "defaultCard",
  },
  (props: Props, { currentNode }) => {
    const { publishDate, excerpt, thumbnail } = props;
    const title = props["jcr:title"];
    const categories = getCategoryLabels(currentNode);

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
          {categories.length > 0 && (
            <div className="news-card__categories">
              {categories.map((cat) => (
                <span key={cat} className="news-card__category">{cat}</span>
              ))}
            </div>
          )}
          <div className="news-card__meta">
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
