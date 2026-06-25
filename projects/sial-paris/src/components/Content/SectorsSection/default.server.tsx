import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import { LucideIcon } from "../../shared/LucideIcon.js";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:sectorItem", displayName: "Sector Item" },
  (props: Props) => {
    const { backgroundImage, iconClass, label, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const bgUrl = backgroundImage ? buildNodeUrl(backgroundImage) : undefined;
    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : "#";

    return (
      <li>
        <a href={href} title={label}>
          <div className="grid">
            {iconClass && (
              <div className="grid-icon">
                <LucideIcon name={iconClass} size={48} />
              </div>
            )}
            {label && <h3 className="grid-title field-title">{label}</h3>}
            <div className="grid-arrow">
              <LucideIcon name="circle-chevron-right" size={20} />
            </div>
            <div className="grid-img img-cover">
              {bgUrl && <img src={bgUrl} alt="" loading="lazy" />}
            </div>
          </div>
        </a>
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
      <section className="component sectors col-12" style={{ /*background: "#FCE003",*/ padding: "60px 0 80px" }}>
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
