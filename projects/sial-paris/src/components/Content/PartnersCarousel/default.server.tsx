import {
  RenderChildren,
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

/** One logo as a swiffy-slider item. */
jahiaComponent(
  { componentType: "view", nodeType: "sialp:partnerLogo", displayName: "Partner Logo" },
  (props: Props) => {
    const { logo, logoExternalUrl, partnerName, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : "#";
    const logoUrl = logo ? buildNodeUrl(logo as unknown as JCRNodeWrapper) : (logoExternalUrl || undefined);

    return (
      <li>
        <a
          href={href}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "110px", padding: "15px" }}
        >
          {logoUrl ? (
            <img src={logoUrl} alt={partnerName ?? "Partenaire"} style={{ maxHeight: "80px", maxWidth: "100%", objectFit: "contain" }} />
          ) : (
            partnerName && <span style={{ fontWeight: 600, color: "#232536", fontSize: "0.9rem", textAlign: "center" }}>{partnerName}</span>
          )}
        </a>
      </li>
    );
  },
);

/** Partners carousel — SXA `partners-carrousel` using swiffy-slider (paged logo strip with nav). */
jahiaComponent(
  { componentType: "view", nodeType: "sialp:partnersCarousel", displayName: "Partners Carousel" },
  ({ heading }: Props, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const count = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("sialp:partnerLogo"),
    ).length;
    const pages = Math.max(1, Math.ceil(count / 6));
    return (
      <section className="component partners-carrousel col-12">
        <div className="component-content container" style={{ maxWidth: "1200px", margin: "0 auto" }}>
          {heading && <h2 className="text-center">{heading}</h2>}
          <div className="swiffy-slider slider-item-show6 slider-item-reveal slider-nav-round slider-nav-outside slider-nav-autohide slider-item-snapstart slider-nav-page slider-indicators-outside slider-indicators-dark">
            <ul className="slider-container">
              <RenderChildren />
            </ul>
            <button type="button" className="slider-nav" aria-label="Précédent"></button>
            <button type="button" className="slider-nav slider-nav-next" aria-label="Suivant"></button>
            <div className="slider-indicators">
              {Array.from({ length: pages }).map((_, i) => (
                <button
                  type="button"
                  key={i}
                  className={i === 0 ? "active" : ""}
                  aria-label={`Page ${i + 1}`}
                ></button>
              ))}
            </div>
          </div>
        </div>
      </section>
    );
  },
);
