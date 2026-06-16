import {
  buildModuleFileUrl,
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";

const FALLBACK_IMAGES = [
  "static/assets/images/slide-1.jpg",
  "static/assets/images/slide-2.jpg",
  "static/assets/images/slide-3.jpg",
];

jahiaComponent(
  { componentType: "view", nodeType: "sialp:heroSlide", displayName: "Hero Slide" },
  () => null,
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

    const slides = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("sialp:heroSlide"),
    );

    const slideData = slides.map((slide: JCRNodeWrapper, idx: number) => {
      const heading = slide.hasProperty("heading") ? slide.getPropertyAsString("heading") : undefined;
      const body = slide.hasProperty("body") ? slide.getPropertyAsString("body") : undefined;
      const ctaLabel = slide.hasProperty("ctaLabel") ? slide.getPropertyAsString("ctaLabel") : undefined;
      const linkType = slide.hasProperty("j:linkType") ? slide.getPropertyAsString("j:linkType") : undefined;
      const href =
        linkType === "external" && slide.hasProperty("j:url")
          ? slide.getPropertyAsString("j:url")
          : "#";

      let imgSrc: string;
      if (slide.hasProperty("backgroundImage")) {
        try {
          const imgNode = slide.getProperty("backgroundImage").getNode() as unknown as JCRNodeWrapper;
          imgSrc = buildNodeUrl(imgNode);
        } catch {
          imgSrc = buildModuleFileUrl(FALLBACK_IMAGES[idx % FALLBACK_IMAGES.length]);
        }
      } else {
        imgSrc = buildModuleFileUrl(FALLBACK_IMAGES[idx % FALLBACK_IMAGES.length]);
      }

      return { heading, body, ctaLabel, href, imgSrc, path: slide.getPath() };
    });

    // If no slides in JCR yet, show fallback slides
    if (slideData.length === 0) {
      return (
        <section className="component carousel col-12 initialized">
          <div className="component-content">
            <div className="carousel-inner">
              <div className="wrapper">
                <ul className="slides" role="list">
                  <li className="slide" role="group">
                    <div className="row">
                      <div className="component Slide">
                        <div className="component-content">
                          <img className="slide-img" src={buildModuleFileUrl("static/assets/images/slide-1.jpg")} alt="" />
                          <div>
                            <h1 className="field-slidesmalltitle">La billetterie pour SIAL Paris 2026 est ouverte !</h1>
                            <div className="field-description field-slidetext">Réservez votre ticket dès aujourd'hui</div>
                            <a className="btn btn-solid-primary mr-20" href="https://badge.sialparis.fr/accueil.htm"><span>Commandez votre ticket</span></a>
                          </div>
                        </div>
                      </div>
                    </div>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </section>
      );
    }

    return (
      <section className="component carousel col-12 initialized">
        <div className="component-content">
          <div className="carousel-inner">
            <div className="wrapper">
              <ul className="slides" role="list">
                {slideData.map((s, idx) => (
                  <li
                    key={s.path}
                    className="slide"
                    role="group"
                    aria-label={s.heading ?? "Slide"}
                    style={{ display: isEdit || idx === 0 ? undefined : "none" }}
                  >
                    <div className="row">
                      <div className="component Slide">
                        <div className="component-content">
                          <img className="slide-img" src={s.imgSrc} alt={s.heading ?? ""} />
                          <div>
                            {s.heading && <h1 className="field-slidesmalltitle">{s.heading}</h1>}
                            {s.body && <div className="field-description field-slidetext">{s.body}</div>}
                            {s.ctaLabel && (
                              <a className="btn btn-solid-primary mr-20" href={s.href}>
                                <span>{s.ctaLabel}</span>
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              {!isEdit && slideData.length > 1 && (
                <div className="nav">
                  <button className="prev-text" aria-label="Précédent" type="button">&#8249;</button>
                  <button className="next-text" aria-label="Suivant" type="button">&#8250;</button>
                </div>
              )}
            </div>
          </div>
          {!isEdit && slideData.length > 1 && (
            <ol className="slider-indicators">
              {slideData.map((s, idx) => (
                <li key={s.path} className={idx === 0 ? "active" : ""}></li>
              ))}
            </ol>
          )}
        </div>
      </section>
    );
  },
);
