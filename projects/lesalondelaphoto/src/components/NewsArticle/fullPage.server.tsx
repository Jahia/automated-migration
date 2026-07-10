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
    name: "fullPage",
    displayName: "Full Article",
  },
  (node: NewsArticleProps) => {
    const title = node["jcr:title"];
    const imageUrl = resolveImageUrl(node.image);
    const altText = node.imageAltText || title || "";
    const dateText = formatDate(node.publishDate);
    const summary = node.summary;
    const body = node.body;
    const tags = node["j:tagList"] || [];

    return (
      <article className="news-article-full">
        {imageUrl && (
          <div className="article-hero">
            <img src={imageUrl} alt={altText} className="slide-img" loading="eager" />
          </div>
        )}
        <div className="container-bp p-20">
          {dateText && <div className="article-date">{dateText}</div>}
          {title && <h1 className="title-n2">{title}</h1>}
          {tags.length > 0 && (
            <div className="article-tags">
              {tags.map((tag) => (
                <span key={tag} className="tag-badge">{tag}</span>
              ))}
            </div>
          )}
          {summary && (
            <div className="article-summary field-description">
              <p>{summary}</p>
            </div>
          )}
          {body && (
            <div
              className="article-body field-description"
              dangerouslySetInnerHTML={{ __html: body }}
            />
          )}
        </div>
      </article>
    );
  },
);
