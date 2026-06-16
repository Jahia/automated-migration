import {
  buildModuleFileUrl,
  buildNodeUrl,
  jahiaComponent,
  useJCRQuery,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:newsListing",
    displayName: "News Listing",
  },
  (props: Props, { renderContext }) => {
    const FALLBACK_IMAGE = buildModuleFileUrl("static/assets/images/news-1.jpg");
    const { heading, ctaLabel, maxItems = 3 } = props;
    const siteKey = renderContext.getSite().getName();

    const ctaHref =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"])
        : props["j:linkType"] === "external"
          ? props["j:url"]
          : undefined;

    const articles: JCRNodeWrapper[] = useJCRQuery({
      query: `SELECT * FROM [sialp:newsArticle] ORDER BY [jcr:created] DESC`,
    });

    const limited = articles?.slice(0, maxItems) ?? [];

    return (
      <section className="component search-results actus container-bp col-12">
        {heading && <h2>{heading}</h2>}
        <ul className="search-result-list">
          {limited.map((article: JCRNodeWrapper) => {
            const title = article.hasProperty("title")
              ? article.getPropertyAsString("title")
              : article.getName();
            const category = article.hasProperty("category")
              ? article.getPropertyAsString("category")
              : undefined;
            const publishDate = article.hasProperty("publishDate")
              ? article.getPropertyAsString("publishDate")
              : undefined;
            const excerpt = article.hasProperty("excerpt")
              ? article.getPropertyAsString("excerpt")
              : undefined;

            const thumbnailNode: JCRNodeWrapper | undefined = article.hasProperty("thumbnail")
              ? (article.getProperty("thumbnail").getNode() as JCRNodeWrapper)
              : undefined;

            const thumbnailUrl = thumbnailNode ? buildNodeUrl(thumbnailNode) : FALLBACK_IMAGE;

            return (
              <li key={article.getPath()}>
                <a href={buildNodeUrl(article)}>
                  <div>
                    <div className="labels">
                      <div>
                        {category && (
                          <div className="label-type field-title">{category}</div>
                        )}
                      </div>
                    </div>
                    <img className="img-cover" src={thumbnailUrl} alt="" />
                    {publishDate && (
                      <div className="text-muted field-date-de-publication">
                        {publishDate}
                      </div>
                    )}
                    <h3 className="field-title">{title}</h3>
                    {excerpt && (
                      <div className="field-description">{excerpt}</div>
                    )}
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
        {ctaLabel && ctaHref && (
          <a href={ctaHref}>{ctaLabel}</a>
        )}
      </section>
    );
  },
);
