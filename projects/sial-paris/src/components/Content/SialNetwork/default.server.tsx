import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type React from "react";
import type { JCRNodeWrapper } from "org.jahia.services.content";
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
            <span className="bullet" aria-hidden="true">•</span>{" "}
            {eventName && <span className="city-name">{eventName}</span>}
            {/* dash is only a separator between the event name and the city */}
            {eventName && city && <span> - </span>}
            {city && <span className="city">{city}</span>}
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
    const { heading, image, ctaLabel, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const ctaHref =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : "#";
    const imgUrl = image ? buildNodeUrl(image as unknown as JCRNodeWrapper) : null;
    return (
      <section className="component content img-content-block-l sial-network col-12">
        <div className="component-content">
          <div className="container-bp">
            <div className="row align-items-center">
              <div className="col-md-5">
                {imgUrl && (
                  <img className="img-cover basic-radius w-100" src={imgUrl} alt={heading ?? "SIAL Network"} />
                )}
              </div>
              <div className="col-md-7">
                {heading && <h2 className="field-titre">{heading}</h2>}
                <div className="row network-events">
                  <RenderChildren />
                </div>
                {ctaLabel && (
                  <div className="mt-4">
                    <a href={ctaHref} className="btn btn-solid-primary">
                      <span>{ctaLabel}</span>
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  },
);
