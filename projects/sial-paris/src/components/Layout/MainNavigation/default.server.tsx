import {
  buildModuleFileUrl,
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:mainNavigation",
    displayName: "Main Navigation",
  },
  (props: Props) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();

    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;

    const pages = getChildNodes(homePage, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("jnt:page"),
    );

    const logoSrc = props.logoImage
      ? buildNodeUrl(props.logoImage)
      : buildModuleFileUrl("static/assets/logo-header.jpg");

    const exposantHref =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"])
        : props["j:linkType"] === "external" && props["j:url"]
          ? props["j:url"]
          : "https://event.sialparis.com/2026/";

    return (
      <header>
        <div id="header" className="container">
          <div className="row">
            {/* Top bar: social icons + community text + CTAs */}
            <div className="component top-bar top-navbar container-fluid">
              <div className="component-content">
                <div className="row align-items-center parent-row">
                  <div className="d-md-down-none socials">
                    {[
                      { icon: "fa-brands fa-linkedin", href: "https://www.linkedin.com/showcase/sial-paris/" },
                      { icon: "fa-brands fa-square-instagram", href: "https://www.instagram.com/sial.paris/" },
                      { icon: "fa-brands fa-x-twitter", href: "https://twitter.com/sial_paris" },
                      { icon: "fa-brands fa-facebook", href: "https://www.facebook.com/sial.paris/" },
                      { icon: "fa-brands fa-youtube", href: "https://www.youtube.com/user/SIALParis" },
                      { icon: "fa-brands fa-whatsapp", href: "https://whatsapp.com/channel/0029VaGDyfY72WTz3iwyrW0x" },
                    ].map(({ icon, href }) => (
                      <a key={href} href={href} target="_blank" rel="noopener noreferrer nofollow">
                        <div><i className={icon}></i></div>
                      </a>
                    ))}
                  </div>
                  <div className="community-text">Rejoignez la communauté #SIALParis</div>
                  <div className="top-ctas">
                    <a href={exposantHref} className="btn-exposer">
                      <span>{props.exposantCtaLabel ?? "Exposez"}</span>
                    </a>
                    <a href="https://event.sialparis.com/2026/" className="btn-espace">
                      <span>Votre espace exposant</span>
                    </a>
                  </div>
                </div>
              </div>
            </div>

            {/* Main header grid: logo | dates | CTA | nav */}
            <div className="component header-navigation container-fluid">
              <div className="component-content">
                <div className="grid">
                  {/* Row 1 Col 1: Logo */}
                  <a href={buildNodeUrl(homePage)} aria-label="SIAL Paris">
                    <img src={logoSrc} alt="SIAL Paris - Inspire Food Business" />
                  </a>

                  {/* Row 1 Col 2: Dates headline */}
                  <div className="title-headline">
                    <strong>17 - 21 octobre 2026</strong>
                    {" - PARIS NORD VILLEPINTE"}
                  </div>

                  {/* Row 1 Col 3: Ticket CTA */}
                  <div className="cta-area">
                    <a href="https://badge.sialparis.fr/accueil.htm" className="btn btn-solid-primary">
                      <span>Commandez votre ticket</span>
                    </a>
                  </div>

                  {/* Spacer (height0) */}
                  <div className="component plain-html height0"></div>

                  {/* Row 2 Col 2-3: Navigation */}
                  <div className="navigation-main">
                    <div className="component navigation initialized">
                      <div className="component-content">
                        <nav>
                          <ul className="clearfix">
                            {pages.map((page: JCRNodeWrapper) => {
                              const subPages = isEdit
                                ? []
                                : getChildNodes(page, -1, 0, (n: JCRNodeWrapper) =>
                                    n.isNodeType("jnt:page"),
                                  );
                              return (
                                <li key={page.getPath()} className={subPages.length > 0 ? "level1 submenu" : "level1"}>
                                  <div className="navigation-title field-navigationtitle">
                                    <a href={buildNodeUrl(page)}>
                                      {page.getPropertyAsString("jcr:title") || page.getName()}
                                    </a>
                                  </div>
                                  {subPages.length > 0 && (
                                    <ul className="clearfix">
                                      {subPages.map((sub: JCRNodeWrapper) => (
                                        <li key={sub.getPath()} className="level2">
                                          <div className="navigation-title field-navigationtitle">
                                            <a href={buildNodeUrl(sub)}>
                                              {sub.getPropertyAsString("jcr:title") || sub.getName()}
                                            </a>
                                          </div>
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </li>
                              );
                            })}
                            {props.visiteurCtaLabel && (
                              <li className="desktop-hidden level1">
                                <div className="navigation-title">
                                  <a href="#">{props.visiteurCtaLabel}</a>
                                </div>
                              </li>
                            )}
                          </ul>
                        </nav>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>
    );
  },
);
