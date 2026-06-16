import {
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:trendsSection",
    displayName: "Trends Section",
  },
  (props: Props) => {
    const { heading, intro, ctaLabel } = props;
    const { currentNode } = useServerContext();

    const cards = getChildNodes(currentNode, -1, 0, (node: JCRNodeWrapper) =>
      node.isNodeType("sialp:trendCard"),
    );

    const ctaHref =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"])
        : props["j:linkType"] === "external" && props["j:url"]
          ? props["j:url"]
          : "#";

    return (
      <section className="component image-list container-bp col-12">
        <div className="component-content">
          <div className="simple-title">
            {heading && <h2>{heading}</h2>}
            {intro && <p>{intro}</p>}
          </div>
          <div className="row">
            {cards.map((card: JCRNodeWrapper) => {
              const cardHeading = card.hasProperty("heading")
                ? card.getPropertyAsString("heading")
                : undefined;
              const cardTag = card.hasProperty("tag")
                ? card.getPropertyAsString("tag")
                : undefined;
              const cardExcerpt = card.hasProperty("excerpt")
                ? card.getPropertyAsString("excerpt")
                : undefined;
              const cardLinkType = card.hasProperty("j:linkType")
                ? card.getPropertyAsString("j:linkType")
                : undefined;
              const cardLinknodeRef =
                cardLinkType === "internal" && card.hasProperty("j:linknode")
                  ? (card.getProperty("j:linknode").getNode() as JCRNodeWrapper)
                  : undefined;
              const cardLinkUrl =
                cardLinkType === "external" && card.hasProperty("j:url")
                  ? card.getPropertyAsString("j:url")
                  : undefined;
              const cardImageNode =
                card.hasProperty("image")
                  ? (card.getProperty("image").getNode() as JCRNodeWrapper)
                  : undefined;

              const cardHref =
                cardLinkType === "internal" && cardLinknodeRef
                  ? buildNodeUrl(cardLinknodeRef)
                  : cardLinkType === "external" && cardLinkUrl
                    ? cardLinkUrl
                    : "#";

              return (
                <div key={card.getPath()} className="col-md-4">
                  <div className="card">
                    <div className="card-img">
                      {cardImageNode && (
                        <img
                          className="img-cover"
                          src={buildNodeUrl(cardImageNode)}
                          alt=""
                        />
                      )}
                    </div>
                    <div className="card-body">
                      {cardTag && <span className="tag">{cardTag}</span>}
                      {cardHeading && <h3>{cardHeading}</h3>}
                      {cardExcerpt && <p>{cardExcerpt}</p>}
                      <a className="btn btn-solid-primary" href={cardHref}>
                        En savoir plus
                      </a>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {ctaLabel && (
            <a className="btn btn-solid-primary" href={ctaHref}>
              {ctaLabel}
            </a>
          )}
        </div>
      </section>
    );
  },
);
