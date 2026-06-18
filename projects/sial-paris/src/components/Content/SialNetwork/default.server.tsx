import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:networkEvent", displayName: "Network Event" },
  (props: Props) => {
    const { eventName, city, eventDates, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
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
  (props: Props, { currentNode }) => {
    const { heading } = props;
    return (
      <section className="component sial-network container-bp col-12">
        <div className="component-content">
          <div className="simple-title">
            {heading && <h2 className="field-titre">{heading}</h2>}
          </div>
          <div className="row">
            <RenderChildren />
          </div>
        </div>
      </section>
    );
  },
);
