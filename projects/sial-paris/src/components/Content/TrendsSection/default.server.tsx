import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:trendCard", displayName: "Trend Card" },
  (props: Props) => {
    const { tag, image, heading, excerpt, ctaLabel, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : "#";

    return (
      <div className="col-md-4">
        <div className="card">
          <div className="card-img">
            {image && <img className="img-cover" src={buildNodeUrl(image)} alt="" />}
          </div>
          <div className="card-body">
            {tag && <span className="tag">{tag}</span>}
            {heading && <h3>{heading}</h3>}
            {excerpt && <p>{excerpt}</p>}
            {ctaLabel && <a className="btn btn-solid-primary" href={href}>{ctaLabel}</a>}
          </div>
        </div>
      </div>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:trendsSection",
    displayName: "Trends Section",
  },
  (props: Props, { currentNode }) => {
    const { heading, intro, ctaLabel, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const ctaHref =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : "#";

    return (
      <section className="component image-list container-bp col-12">
        <div className="component-content">
          <div className="simple-title">
            {heading && <h2>{heading}</h2>}
            {intro && <p>{intro}</p>}
          </div>
          <div className="row">
            <RenderChildren />
          </div>
          {ctaLabel && (
            <a className="btn btn-solid-primary" href={ctaHref}>{ctaLabel}</a>
          )}
        </div>
      </section>
    );
  },
);
