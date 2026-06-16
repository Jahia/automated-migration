import {
  jahiaComponent,
  buildNodeUrl,
  getChildNodes,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

// Child partner logo view
import { jahiaComponent as jc2 } from "@jahia/javascript-modules-library";

jc2(
  {
    componentType: "view",
    nodeType: "sialp:partnerLogo",
    displayName: "Partner Logo",
  },
  (props: Props) => {
    const { logo, partnerName } = props;

    const href =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"])
        : props["j:linkType"] === "external"
          ? props["j:url"]
          : undefined;

    const logoUrl = logo ? buildNodeUrl(logo) : undefined;

    return (
      <li className="row">
        <a className="content col-4 col-md-3" href={href ?? "#"}>
          {logoUrl && <img src={logoUrl} alt={partnerName ?? "Partner"} />}
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
  ({ heading }: Props, { renderContext, currentNode }) => {
    const isEdit = renderContext.isEditMode();

    const partners = getChildNodes(
      currentNode,
      -1,
      0,
      (n: JCRNodeWrapper) => n.isNodeType("sialp:partnerLogo"),
    );

    return (
      <section className="component partners-carrousel">
        <div className="component-content">
          {heading && <h2>{heading}</h2>}
          <div className="swiffy-slider slider-nav-page slider-indicators-outside slider-indicators-dark slider-nav-animation">
            <ul className="slider-container" role="list">
              {partners.map((partner: JCRNodeWrapper) => {
                const logoNode = partner.hasProperty("logo")
                  ? (partner.getProperty("logo").getNode() as JCRNodeWrapper)
                  : undefined;
                const logoUrl = logoNode ? buildNodeUrl(logoNode) : undefined;
                const partnerName = partner.hasProperty("partnerName")
                  ? partner.getPropertyAsString("partnerName")
                  : "";
                const linkType = partner.hasProperty("j:linkType")
                  ? partner.getPropertyAsString("j:linkType")
                  : undefined;
                const linkNodeProp =
                  linkType === "internal" && partner.hasProperty("j:linknode")
                    ? (partner.getProperty("j:linknode").getNode() as JCRNodeWrapper)
                    : undefined;
                const externalUrl =
                  linkType === "external" && partner.hasProperty("j:url")
                    ? partner.getPropertyAsString("j:url")
                    : undefined;
                const href = linkNodeProp
                  ? buildNodeUrl(linkNodeProp)
                  : externalUrl ?? "#";

                return (
                  <li key={partner.getPath()} className="row">
                    <a className="content col-4 col-md-3" href={href}>
                      {logoUrl && <img src={logoUrl} alt={partnerName} />}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </section>
    );
  },
);
