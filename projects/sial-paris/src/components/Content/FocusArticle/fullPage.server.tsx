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
    displayName: "Focus Article Full Page",
    name: "fullPage",
  },
  (props: Props, { currentNode }) => {
    const { publishDate, excerpt, body, thumbnail } = props;
    const title = props["jcr:title"];
    const categories = getCategoryLabels(currentNode);
    const heroUrl = thumbnail ? buildNodeUrl(thumbnail) : undefined;
    const formattedDate = publishDate
      ? (() => {
          const d = new Date(publishDate);
          return isNaN(d.getTime())
            ? publishDate
            : d.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
        })()
      : undefined;

    return (
      <article className="article-full">
        <div
          className="article-full__hero"
          style={heroUrl ? { backgroundImage: `url(${heroUrl})` } : undefined}
        >
          <div className="article-full__hero-overlay">
            <div className="container">
              {categories.length > 0 && (
                <div className="article-full__categories">
                  {categories.map((cat) => (
                    <span key={cat} className="article-full__category">{cat}</span>
                  ))}
                </div>
              )}
              {formattedDate && (
                <time dateTime={publishDate} className="article-full__date">{formattedDate}</time>
              )}
              {title && <h1 className="article-full__title">{title}</h1>}
            </div>
          </div>
        </div>
        <div className="container">
          <div className="article-full__content">
            {excerpt && <p className="article-full__lead">{excerpt}</p>}
            {body && (
              <div
                className="article-full__body richtext"
                dangerouslySetInnerHTML={{ __html: body }}
              />
            )}
          </div>
        </div>
      </article>
    );
  },
);
