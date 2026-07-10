import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type React from "react";
import { LucideIcon } from "../../shared/LucideIcon.js";
import type { Props } from "./types.js";

const iconBoxStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: "120px",
  height: "120px",
  backgroundColor: "#fff",
  borderRadius: "20px",
  boxShadow: "0 5px 24px rgba(0,0,0,.12)",
  margin: "0 auto 16px",
  padding: "20px",
  fontSize: "54px",
  lineHeight: "84px",
  transition: "color .4s, transform .4s",
};

jahiaComponent(
  { componentType: "view", nodeType: "sialp:visitorProfile", displayName: "Visitor Profile" },
  (props: Props) => {
    const { icon, iconClass, heading, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : "#";

    return (
      <div className="col-md-3 col-6">
        <a href={href} style={{ textDecoration: "none", color: "inherit", display: "block", textAlign: "center" }}>
          {icon ? (
            <i style={iconBoxStyle}>
              <img src={buildNodeUrl(icon)} alt="" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            </i>
          ) : iconClass ? (
            <span style={iconBoxStyle}>
              <LucideIcon name={iconClass} size={54} />
            </span>
          ) : null}
          {heading && <h3 className="field-titre">{heading}</h3>}
        </a>
      </div>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:visitorProfiles",
    displayName: "Visitor Profiles",
  },
  (props: Props, { currentNode }) => {
    const { heading } = props;
    return (
      <section className="component quicklinks container bg-gray-1 col-12">
        <div className="component-content">
          <div className="container-bp">
            {heading && <h2>{heading}</h2>}
            <div className="row justify-content-center">
              <RenderChildren />
            </div>
          </div>
        </div>
      </section>
    );
  },
);
