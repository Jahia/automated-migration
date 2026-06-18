import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:sectorItem", displayName: "Sector Item" },
  (props: Props) => {
    const { backgroundImage, icon, label, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const bgUrl = backgroundImage ? buildNodeUrl(backgroundImage) : undefined;
    const iconUrl = icon ? buildNodeUrl(icon) : undefined;
    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : undefined;

    const inner = (
      <div className="grid">
        <div className="grid-img">
          {bgUrl && <img src={bgUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
        </div>
        {iconUrl && (
          <div className="grid-icon">
            <img src={iconUrl} alt="" style={{ width: "54px", height: "54px" }} />
          </div>
        )}
        {label && <div className="grid-title">{label}</div>}
        <div className="grid-arrow"><i className="fa fa-angle-right" /></div>
      </div>
    );

    return (
      <li>
        {href ? <a href={href}>{inner}</a> : <div className="sector-no-link">{inner}</div>}
      </li>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:sectorsSection",
    displayName: "Sectors Section",
  },
  (props: Props) => {
    const { heading } = props;
    return (
      <section className="component sectors col-12" style={{ background: "#FCE003", padding: "60px 0 80px" }}>
        <div className="component-content container-bp">
          {heading && (
            <h2 style={{ color: "#000", marginBottom: "40px", textAlign: "center" }}>{heading}</h2>
          )}
          <ul className="search-result-list" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            <RenderChildren />
          </ul>
        </div>
      </section>
    );
  },
);
