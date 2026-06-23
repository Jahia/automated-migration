import {
  buildModuleFileUrl,
  buildNodeUrl,
  getChildNodes,
  getSiteLocales,
  jahiaComponent,
  RenderChild,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

const getNavItems = (node: JCRNodeWrapper): JCRNodeWrapper[] =>
  getChildNodes(node, -1, 0, (n: JCRNodeWrapper) => {
    if (!n.isNodeType("jmix:navMenuItem")) return false;
    if (n.isNodeType("jmix:navMenu")) return false;
    return true;
  });

const getItemUrl = (node: JCRNodeWrapper): string => {
  try {
    if (node.isNodeType("jnt:page")) return buildNodeUrl(node);
    if (node.isNodeType("jnt:nodeLink") && node.hasProperty("j:node"))
      return buildNodeUrl(node.getProperty("j:node").getNode() as JCRNodeWrapper);
    if (node.isNodeType("jnt:externalLink") && node.hasProperty("j:url"))
      return node.getProperty("j:url").getString();
  } catch (_) {}
  return "#";
};

const getItemTitle = (node: JCRNodeWrapper): string => {
  try {
    if (node.isNodeType("jnt:nodeLink") && node.hasProperty("j:node")) {
      const ref = node.getProperty("j:node").getNode() as JCRNodeWrapper;
      if (ref.hasProperty("jcr:title")) return ref.getProperty("jcr:title").getString();
      return ref.getName();
    }
    if (node.hasProperty("jcr:title")) return node.getProperty("jcr:title").getString();
  } catch (_) {}
  return node.getName();
};

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:mainNavigation",
    displayName: "Main Navigation",
  },
  (props: Props) => {
    const { renderContext, currentResource } = useServerContext();
    const isEdit = renderContext.isEditMode();

    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;
    const mainNode = renderContext.getMainResource().getNode() as JCRNodeWrapper;
    const level1Items = getNavItems(homePage);

    const currentLang = currentResource.getLocale().getLanguage();
    const siteLocales = getSiteLocales();
    const showLangSwitcher = Object.keys(siteLocales).length > 1;

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
            <RenderChild name="topBar" />

            <div className="component header-navigation container-fluid">
              <div className="component-content">
                <div className="grid">
                  <a href={buildNodeUrl(homePage)} aria-label="SIAL Paris">
                    <img src={logoSrc} alt="SIAL Paris - Inspire Food Business" />
                  </a>

                  <div className="title-headline">
                    {props.dateText && <strong>{props.dateText}</strong>}
                    {props.locationText && <>{" - "}{props.locationText}</>}
                  </div>

                  {ticketHref && props.ticketCtaLabel && (
                    <div className="cta-area">
                      <a href={ticketHref} className="btn btn-solid-primary">
                        <span>{props.ticketCtaLabel}</span>
                      </a>
                    </div>
                  )}

                  <div className="component plain-html height0"></div>

                  <button
                    type="button"
                    className="nav-burger"
                    data-mobile-nav-toggle
                    aria-label="Menu"
                    aria-expanded="false"
                    aria-controls="main-nav"
                  >
                    <span aria-hidden="true"></span>
                  </button>

                  <div className="navigation-main">
                    <div className="component navigation initialized">
                      <div className="component-content">
                        <nav id="main-nav" role="navigation" aria-label="Main navigation" data-expanded="false">
                          <ul className="clearfix">
                            {level1Items.map((item: JCRNodeWrapper) => {
                              const isMenuText = item.isNodeType("jnt:navMenuText");
                              const level2Items = isEdit || isMenuText ? [] : getNavItems(item);
                              const hasL2 = level2Items.length > 0;
                              const isActive =
                                !isMenuText &&
                                item.isNodeType("jnt:page") &&
                                (item.getPath() === mainNode.getPath() ||
                                  mainNode.getPath().startsWith(item.getPath() + "/"));
                              const extraClass = isMenuText ? ` nav-text-${item.getName()}` : "";

                              return (
                                <li key={item.getPath()} className={`level1${hasL2 ? " submenu" : ""}${extraClass}`}>
                                  <div className="navigation-title field-navigationtitle">
                                    {isMenuText ? (
                                      <span>{getItemTitle(item)}</span>
                                    ) : (
                                      <a
                                        href={getItemUrl(item)}
                                        data-nav-path={item.getPath()}
                                        aria-current={isActive ? "page" : undefined}
                                      >
                                        {getItemTitle(item)}
                                      </a>
                                    )}
                                  </div>
                                  {hasL2 && (
                                    <ul className="clearfix">
                                      {level2Items.map((sub: JCRNodeWrapper) => {
                                        const level3Items = isEdit ? [] : getNavItems(sub);
                                        const hasL3 = level3Items.length > 0;
                                        const isSubActive =
                                          sub.isNodeType("jnt:page") &&
                                          (sub.getPath() === mainNode.getPath() ||
                                            mainNode.getPath().startsWith(sub.getPath() + "/"));

                                        return (
                                          <li key={sub.getPath()} className={`level2${hasL3 ? " submenu" : ""}`}>
                                            <div className="navigation-title field-navigationtitle">
                                              <a
                                                href={getItemUrl(sub)}
                                                data-nav-path={sub.getPath()}
                                                aria-current={isSubActive ? "page" : undefined}
                                              >
                                                {getItemTitle(sub)}
                                              </a>
                                            </div>
                                            {hasL3 && (
                                              <ul className="clearfix level3-dropdown">
                                                {level3Items.map((deep: JCRNodeWrapper) => (
                                                  <li key={deep.getPath()} className="level3">
                                                    <div className="navigation-title field-navigationtitle">
                                                      <a
                                                        href={getItemUrl(deep)}
                                                        data-nav-path={deep.getPath()}
                                                      >
                                                        {getItemTitle(deep)}
                                                      </a>
                                                    </div>
                                                  </li>
                                                ))}
                                              </ul>
                                            )}
                                          </li>
                                        );
                                      })}
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

                          {showLangSwitcher && (
                            <ul aria-label="Language selection" className="lang-switcher" style={{ display: "flex", listStyle: "none", gap: "0.5rem", padding: "0.5rem 1rem" }}>
                              {Object.keys(siteLocales).map((langCode) => {
                                const isCurrent = langCode === currentLang;
                                const url = buildNodeUrl(
                                  renderContext.getMainResource().getNode() as JCRNodeWrapper,
                                  { language: langCode },
                                );
                                return (
                                  <li key={langCode}>
                                    <a
                                      href={url}
                                      lang={langCode.toUpperCase()}
                                      aria-current={isCurrent ? "true" : undefined}
                                      style={{ fontWeight: isCurrent ? 700 : 400, textTransform: "uppercase", fontSize: "0.75rem" }}
                                    >
                                      {langCode.toUpperCase()}
                                    </a>
                                  </li>
                                );
                              })}
                            </ul>
                          )}
                        </nav>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <script dangerouslySetInnerHTML={{ __html: `(function(){
  var toggle = document.querySelector('[data-mobile-nav-toggle]');
  var navMain = document.querySelector('.navigation-main');
  var nav = document.getElementById('main-nav');
  var mq = window.matchMedia('(max-width: 1199.98px)');
  function closeMenu(){
    if (navMain) navMain.classList.remove('is-open');
    document.body.style.overflow = '';
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }
  // Hamburger: slide the off-canvas panel in/out (theme '.is-open')
  if (toggle && navMain) {
    toggle.addEventListener('click', function(e) {
      e.stopPropagation();
      var open = navMain.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
      document.body.style.overflow = open ? 'hidden' : '';
    });
  }
  // Mobile accordion: tap a submenu parent to expand its children ('.submenu-open')
  document.querySelectorAll('#main-nav li.level1.submenu > .navigation-title, #main-nav li.level2.submenu > .navigation-title').forEach(function(t) {
    t.addEventListener('click', function(e) {
      if (!mq.matches) return; // desktop uses :hover
      e.preventDefault();
      t.parentElement.classList.toggle('submenu-open');
    });
  });
  // Close the panel when a real navigation link is followed
  if (nav) nav.querySelectorAll('a[href]:not([href="#"])').forEach(function(a) {
    a.addEventListener('click', closeMenu);
  });
  // Close on click outside the panel
  document.addEventListener('click', function(e) {
    if (navMain && navMain.classList.contains('is-open')
        && !navMain.contains(e.target) && (!toggle || !toggle.contains(e.target))) {
      closeMenu();
    }
  });
  // Reset state when crossing back to desktop
  mq.addEventListener('change', function(ev) {
    if (!ev.matches) {
      closeMenu();
      document.querySelectorAll('.level1.submenu-open, .level2.submenu-open').forEach(function(x) { x.classList.remove('submenu-open'); });
    }
  });
  var raw = window.location.pathname;
  var jcrPath = raw.replace(/^\\/(?:fr|en|es)(\\/|$)/, '$1').replace(/\\.html$/, '').replace(/\\/$/, '') || '/';
  document.querySelectorAll('[data-nav-path]').forEach(function(link) {
    var navPath = link.getAttribute('data-nav-path');
    if (jcrPath === navPath || jcrPath.startsWith(navPath + '/'))
      link.setAttribute('aria-current', 'page');
  });
})();` }} />
      </header>
    );
  },
);
