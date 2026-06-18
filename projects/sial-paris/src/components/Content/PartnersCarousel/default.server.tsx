import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:partnerLogo", displayName: "Partner Logo" },
  (props: Props) => {
    const { logo, partnerName, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : "#";
    const logoUrl = logo ? buildNodeUrl(logo as unknown as JCRNodeWrapper) : undefined;

    return (
      <li style={{ flexShrink: 0 }}>
        <a href={href} style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "20px", minHeight: "80px", minWidth: "160px", border: "1px solid #e0e0e0", borderRadius: "8px" }}>
          {logoUrl
            ? <img src={logoUrl} alt={partnerName ?? "Partner"} style={{ maxHeight: "60px", maxWidth: "140px", objectFit: "contain" }} />
            : partnerName && <span style={{ fontWeight: 600, color: "#232536", fontSize: "0.9rem", textAlign: "center" }}>{partnerName}</span>
          }
        </a>
      </li>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:partnersCarousel",
    displayName: "Partners Carousel",
  },
  ({ heading }: Props, { currentNode }) => {
    return (
      <section className="component partners-carrousel">
        <div className="component-content container" style={{ maxWidth: "1140px", margin: "0 auto" }}>
          {heading && <h2>{heading}</h2>}
          <ul style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", listStyle: "none", padding: 0, margin: 0, gap: "20px" }}>
            <RenderChildren />
          </ul>
        </div>
      </section>
    );
  },
);
