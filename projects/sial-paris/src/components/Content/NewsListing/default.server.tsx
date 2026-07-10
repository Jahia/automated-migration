import {
  buildNodeUrl,
  jahiaComponent,
  Render,
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
    const { heading, ctaLabel, maxItems = 3 } = props;

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
          {limited.map((article: JCRNodeWrapper) => (
            <li key={article.getPath()}>
              <Render node={article} view="card" />
            </li>
          ))}
        </ul>
        {ctaLabel && ctaHref && <a href={ctaHref}>{ctaLabel}</a>}
      </section>
    );
  },
);
