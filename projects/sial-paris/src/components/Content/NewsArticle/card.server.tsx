import { buildModuleFileUrl, buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
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

/**
 * News Article card (listing). Uses the shared `.news-card` structure (styled in
 * Layout.tsx) so the whole card is one contained unit: image on top, then a body
 * holding the category chips, date, title and excerpt — all inside the card.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:newsArticle",
    name: "card",
    displayName: "News Article Card (Listing)",
  },
  (props: Props, { currentNode }) => {
    const { publishDate, excerpt, thumbnail } = props;
    const title = props["jcr:title"];
    const categories = getCategoryLabels(currentNode);
    const thumbs = ["news-1.jpg", "news-2.jpg", "news-3.jpg"];
    const idx = currentNode.getPath().length % thumbs.length;
    const thumbnailUrl = thumbnail
      ? buildNodeUrl(thumbnail)
      : buildModuleFileUrl("static/assets/images/" + thumbs[idx]);

    const formattedDate = publishDate
      ? (() => {
          const d = new Date(publishDate);
          return isNaN(d.getTime())
            ? publishDate
            : d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
        })()
      : undefined;

    const url = buildNodeUrl(currentNode);

    return (
      <article className="news-card">
        <a href={url} aria-hidden="true" tabIndex={-1}>
          <img className="news-card__image" src={thumbnailUrl} alt="" loading="lazy" />
        </a>
        <div className="news-card__body">
          {categories.length > 0 && (
            <div className="news-card__categories">
              {categories.map((cat) => (
                <span key={cat} className="news-card__category">{cat}</span>
              ))}
            </div>
          )}
          {formattedDate && <span className="news-card__date">{formattedDate}</span>}
          {title && (
            <h3 className="news-card__title">
              <a href={url} className="news-card__title-link">{title}</a>
            </h3>
          )}
          {excerpt && <p className="news-card__excerpt">{excerpt}</p>}
        </div>
      </article>
    );
  },
);
