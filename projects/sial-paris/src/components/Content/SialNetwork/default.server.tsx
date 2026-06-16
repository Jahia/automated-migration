import {
  jahiaComponent,
  buildNodeUrl,
  getChildNodes,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

// Child network event view
import { jahiaComponent as jc2 } from "@jahia/javascript-modules-library";

jc2(
  {
    componentType: "view",
    nodeType: "sialp:networkEvent",
    displayName: "Network Event",
  },
  (props: Props) => {
    const { eventName, city, eventDates } = props;

    const href =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"])
        : props["j:linkType"] === "external"
          ? props["j:url"]
          : "#";

    return (
      <div className="col-md-4 col-6">
        <div className="network-card">
          <a href={href}>
            {eventName && <span className="city-name">{eventName}</span>}
            {city && <span> - {city}</span>}
            {eventDates && <div className="dates">{eventDates}</div>}
          </a>
        </div>
      </div>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:sialNetwork",
    displayName: "SIAL Network",
  },
  (props: Props, { renderContext, currentNode }) => {
    const { heading } = props;

    const events = getChildNodes(
      currentNode,
      -1,
      0,
      (n: JCRNodeWrapper) => n.isNodeType("sialp:networkEvent"),
    );

    const ctaLinkType = currentNode.hasProperty("j:linkType")
      ? currentNode.getPropertyAsString("j:linkType")
      : undefined;
    const ctaLinkNode =
      ctaLinkType === "internal" && currentNode.hasProperty("j:linknode")
        ? (currentNode.getProperty("j:linknode").getNode() as JCRNodeWrapper)
        : undefined;
    const ctaExternalUrl =
      ctaLinkType === "external" && currentNode.hasProperty("j:url")
        ? currentNode.getPropertyAsString("j:url")
        : undefined;
    const ctaHref = ctaLinkNode
      ? buildNodeUrl(ctaLinkNode)
      : ctaExternalUrl ?? "#";

    const ctaLabel = currentNode.hasProperty("ctaLabel")
      ? currentNode.getPropertyAsString("ctaLabel")
      : undefined;

    return (
      <section className="component sial-network container-bp col-12">
        <div className="component-content">
          <div className="simple-title">
            {heading && <h2 className="field-titre">{heading}</h2>}
          </div>
          <div className="row">
            {events.map((event: JCRNodeWrapper) => {
              const eventName = event.hasProperty("eventName")
                ? event.getPropertyAsString("eventName")
                : "";
              const city = event.hasProperty("city")
                ? event.getPropertyAsString("city")
                : "";
              const eventDates = event.hasProperty("eventDates")
                ? event.getPropertyAsString("eventDates")
                : "";
              const evtLinkType = event.hasProperty("j:linkType")
                ? event.getPropertyAsString("j:linkType")
                : undefined;
              const evtLinkNode =
                evtLinkType === "internal" && event.hasProperty("j:linknode")
                  ? (event.getProperty("j:linknode").getNode() as JCRNodeWrapper)
                  : undefined;
              const evtExtUrl =
                evtLinkType === "external" && event.hasProperty("j:url")
                  ? event.getPropertyAsString("j:url")
                  : undefined;
              const eventHref = evtLinkNode
                ? buildNodeUrl(evtLinkNode)
                : evtExtUrl ?? "#";

              return (
                <div key={event.getPath()} className="col-md-4 col-6">
                  <div className="network-card">
                    <a href={eventHref}>
                      <span className="city-name">{eventName}</span>
                      {city && <span> - {city}</span>}
                      {eventDates && <div className="dates">{eventDates}</div>}
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
          {ctaLabel && (
            <a className="btn btn-outline-dark" href={ctaHref}>
              {ctaLabel}
            </a>
          )}
        </div>
      </section>
    );
  },
);
