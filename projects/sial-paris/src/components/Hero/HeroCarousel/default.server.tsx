import {
  RenderChildren,
  buildModuleFileUrl,
  buildNodeUrl,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

const FALLBACK_IMAGES = [
  "static/assets/images/slide-1.jpg",
  "static/assets/images/slide-2.jpg",
  "static/assets/images/slide-3.jpg",
];

jahiaComponent(
  { componentType: "view", nodeType: "sialp:heroSlide", displayName: "Hero Slide" },
  (props: Props) => {
    const { heading, body, ctaLabel, "j:linkType": linkType, "j:linknode": linknode, "j:url": url } = props;
    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : "#";

    const imgSrc = props.backgroundImage
      ? buildNodeUrl(props.backgroundImage)
      : buildModuleFileUrl(FALLBACK_IMAGES[0]);

    return (
      <li className="slide" role="group" aria-label={heading ?? "Slide"}>
        <div className="row">
          <div className="component Slide">
            <div className="component-content">
              <img className="slide-img" src={imgSrc} alt={heading ?? ""} />
              <div>
                {heading && <h1 className="field-slidesmalltitle">{heading}</h1>}
                {body && <div className="field-description field-slidetext">{body}</div>}
                {ctaLabel && (
                  <a className="btn btn-solid-primary mr-20" href={href}>
                    <span>{ctaLabel}</span>
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      </li>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:heroCarousel",
    displayName: "Hero Carousel",
  },
  (_props, { currentNode }) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();

    return (
      <section className="component carousel col-12 initialized">
        <div className="component-content">
          <div className="carousel-inner">
            <div className="wrapper">
              <ul className="slides" role="list">
                <RenderChildren />
              </ul>
              {!isEdit && (
                <div className="nav">
                  <button className="prev-text" aria-label="Précédent" type="button">&#8249;</button>
                  <button className="next-text" aria-label="Suivant" type="button">&#8250;</button>
                </div>
              )}
            </div>
          </div>
          {!isEdit && <ol className="slider-indicators" />}
        </div>
      </section>
    );
  },
);
