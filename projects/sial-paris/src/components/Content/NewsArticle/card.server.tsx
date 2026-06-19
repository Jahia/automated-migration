import { buildModuleFileUrl, buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:newsArticle",
    name: "card",
    displayName: "News Article Card (Listing)",
  },
  (props: Props, { currentNode }) => {
    const { title, category, publishDate, excerpt, thumbnail } = props;
    const fallbackImage = buildModuleFileUrl("static/assets/images/news-1.jpg");
    const thumbnailUrl = thumbnail ? buildNodeUrl(thumbnail) : fallbackImage;

    const formattedDate = publishDate
      ? (() => {
          const d = new Date(publishDate);
          return isNaN(d.getTime())
            ? publishDate
            : d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
        })()
      : undefined;

    return (
      <a href={buildNodeUrl(currentNode)}>
        <div>
          <div className="labels">
            <div>
              {category && <div className="label-type field-title">{category}</div>}
            </div>
          </div>
          <img className="img-cover" src={thumbnailUrl} alt="" />
          {formattedDate && (
            <div className="text-muted field-date-de-publication">{formattedDate}</div>
          )}
          {title && <h3 className="field-title">{title}</h3>}
          {excerpt && <div className="field-description">{excerpt}</div>}
        </div>
      </a>
    );
  },
);
