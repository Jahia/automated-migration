import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { NewsArticleProps } from "./types.js";

function resolveImageUrl(image: JCRNodeWrapper | undefined): string | undefined {
  if (!image) return undefined;
  try {
    return buildNodeUrl(image);
  } catch {
    return undefined;
  }
}

function formatDate(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return raw;
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch {
    return raw;
  }
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:newsArticle",
    name: "default",
    displayName: "News Card",
  },
  (node: NewsArticleProps) => {
    const title = node["jcr:title"];
    const imageUrl = resolveImageUrl(node.image);
    const altText = node.imageAltText || title || "";
    const dateText = formatDate(node.publishDate);
    const summary = node.summary;

    return (
      <div className="news-card">
        {imageUrl && (
          <div className="card-img">
            <img src={imageUrl} alt={altText} className="img-cover" loading="lazy" />
          </div>
        )}
        <div className="card">
          <div className="card-body">
            {dateText && <div className="news-date">{dateText}</div>}
            {title && <h3 className="field-picturegriditemtitre">{title}</h3>}
            {summary && <p className="field-description">{summary}</p>}
          </div>
        </div>
      </div>
    );
  },
);
