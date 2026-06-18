import {
  buildModuleFileUrl,
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
  RenderChild,
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
      n.isNodeType("jnt:page") || n.isNodeType("jnt:navMenuText"),
    );

    const logoSrc = props.logoImage
      ? buildNodeUrl(props.logoImage)
      : buildModuleFileUrl("static/assets/logo-header.jpg");

    const ticketHref =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"])
        : props["j:linkType"] === "external" && props["j:url"]
          ? props["j:url"]
          : undefined;

    return (
      <header>
        <div id="header" className="container">
          <div className="row">
            {/* Top bar — rendered from its own editable topBar child node */}
            <RenderChild name="topBar" />

            {/* Main header grid: logo | dates | CTA | nav */}
            <div className="component header-navigation container-fluid">
              <div className="component-content">
                <div className="grid">
                  {/* Row 1 Col 1: Logo */}
                  <a href={buildNodeUrl(homePage)} aria-label="SIAL Paris">
                    <img src={logoSrc} alt="SIAL Paris - Inspire Food Business" />
                  </a>

                  {/* Row 1 Col 2: Dates + location headline */}
                  <div className="title-headline">
                    {props.dateText && <strong>{props.dateText}</strong>}
                    {props.locationText && <>{" - "}{props.locationText}</>}
                  </div>

                  {/* Row 1 Col 3: Ticket CTA */}
                  {ticketHref && props.ticketCtaLabel && (
                    <div className="cta-area">
                      <a href={ticketHref} className="btn btn-solid-primary">
                        <span>{props.ticketCtaLabel}</span>
                      </a>
                    </div>
                  )}

                  {/* Spacer (height0) */}
                  <div className="component plain-html height0"></div>

                  {/* Row 2 Col 2-3: Navigation */}
                  <div className="navigation-main">
                    <div className="component navigation initialized">
                      <div className="component-content">
                        <nav>
                          <ul className="clearfix">
                            {pages.map((page: JCRNodeWrapper) => {
                              const isMenuText = page.isNodeType("jnt:navMenuText");
                              const subPages = isEdit || isMenuText
                                ? []
                                : getChildNodes(page, -1, 0, (n: JCRNodeWrapper) =>
                                    n.isNodeType("jnt:page"),
                                  );
                              const href = isMenuText ? "#" : buildNodeUrl(page);
                              const extraClass = isMenuText ? ` nav-text-${page.getName()}` : "";
                              return (
                                <li key={page.getPath()} className={subPages.length > 0 ? `level1 submenu${extraClass}` : `level1${extraClass}`}>
                                  <div className="navigation-title field-navigationtitle">
                                    <a href={href}>
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
