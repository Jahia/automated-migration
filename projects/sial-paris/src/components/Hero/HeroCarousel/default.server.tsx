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
      : (props.backgroundImageUrl || buildModuleFileUrl(FALLBACK_IMAGES[0]));

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
                  {/* Anchors (not buttons): the theme styles a.prev-text/a.next-text
                      and injects the FontAwesome chevron via ::after. */}
                  <a className="prev-text" href="#" role="button" aria-label="Précédent"></a>
                  <a className="next-text" href="#" role="button" aria-label="Suivant"></a>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    );
  },
);
