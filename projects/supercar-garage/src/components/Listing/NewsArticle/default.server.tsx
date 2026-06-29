import {
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { NewsArticleProps } from "./types.js";

interface Cat {
  name: string;
  title: string;
}

/** Read j:defaultCategory and split into theme vs type by the branch the
 *  category lives in (actualites-themes / actualites-types). */
function readCategories(node: JCRNodeWrapper): { theme?: Cat; type?: Cat } {
  const out: { theme?: Cat; type?: Cat } = {};
  try {
    if (!node.hasProperty("j:defaultCategory")) return out;
    const values = node.getProperty("j:defaultCategory").getValues();
    for (let i = 0; i < values.length; i++) {
      let cat: JCRNodeWrapper;
      try {
        cat = values[i].getNode() as JCRNodeWrapper;
      } catch (_) {
        continue;
      }
      const path = cat.getPath();
      const title = cat.hasProperty("jcr:title")
        ? cat.getProperty("jcr:title").getString()
        : cat.getName();
      const entry: Cat = { name: cat.getName(), title };
      if (path.includes("actualites-themes")) out.theme = entry;
      else if (path.includes("actualites-types")) out.type = entry;
    }
  } catch (_) {}
  return out;
}

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
    const cardUrl = buildNodeUrl(currentNode);
    const imageSrc = image ? buildNodeUrl(image) : undefined;
    const { theme, type } = readCategories(currentNode);

    let formattedDate: string | undefined;
    if (publishDate) {
      try {
        formattedDate = new Date(publishDate).toLocaleDateString("fr-FR", {
          year: "numeric",
          month: "long",
          day: "numeric",
        });
      } catch (_) {
        formattedDate = publishDate;
      }
    }

    return (
      <article
        className="search-result-item"
        data-theme={theme?.name ?? ""}
        data-type={type?.name ?? ""}
      >
        <a href={cardUrl} className="search-result-link">
          <div className="labels">
            {imageSrc && <img src={imageSrc} alt={title ?? ""} loading="lazy" />}
            <div>
              {type && <span className="label-type">{type.title}</span>}
              {theme && <span className="label-theme">{theme.title}</span>}
            </div>
          </div>

          {formattedDate && (
            <time className="text-muted" dateTime={publishDate}>
              {formattedDate}
            </time>
          )}

          {title && <h3 className="field-title">{title}</h3>}

          {summary && (
            <div
              className="field-description"
              dangerouslySetInnerHTML={{ __html: summary }}
            />
          )}

          {author && <p className="text-muted">{author}</p>}
        </a>
      </article>
    );
  },
);
