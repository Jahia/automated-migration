import {
  buildModuleFileUrl,
  buildNodeUrl,
  getChildNodes,
  getSiteLocales,
  jahiaComponent,
  Render,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { MainNavigationProps } from "./types.js";
import styles from "./mainNavigation.module.css";

// Pages excluded from main nav (they appear in the TopBar instead)
const NAV_EXCLUDED = new Set(["espace-exposant", "presse"]);

const getNavItems = (node: JCRNodeWrapper, isHome = false): JCRNodeWrapper[] =>
  getChildNodes(node, -1, 0, (n: JCRNodeWrapper) => {
    if (!n.isNodeType("jnt:page")) return false;
    // For home level-1: exclude topbar-only pages
    if (isHome && NAV_EXCLUDED.has(n.getName())) return false;
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
    nodeType: "usg:mainNavigation",
    displayName: "Main Navigation",
  },
  (props: MainNavigationProps, { currentNode }) => {
    const { renderContext, currentResource } = useServerContext();
    const isEdit = renderContext.isEditMode();

    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;
    const mainNode = renderContext.getMainResource().getNode() as JCRNodeWrapper;
    const level1Items = getNavItems(homePage, true);

    const currentLang = currentResource.getLocale().getLanguage();
    const siteLocales = getSiteLocales();
    const showLangSwitcher = Object.keys(siteLocales).length > 1;

    const logoSrc = props.logo
      ? buildNodeUrl(props.logo)
      : buildModuleFileUrl("static/assets/logo-header.svg");

    const logoHref =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"])
        : props["j:linkType"] === "external" && props["j:url"]
          ? props["j:url"]
          : buildNodeUrl(homePage);

    // CTA buttons come from child usg:ctaButton nodes (link + label per button)
    const ctaButtons = getChildNodes(
      currentNode,
      -1,
      0,
      (n: JCRNodeWrapper) => n.isNodeType("usg:ctaButton"),
    );

    const getCtaHref = (n: JCRNodeWrapper): string => {
      try {
        const lt = n.hasProperty("j:linkType") ? n.getProperty("j:linkType").getString() : "none";
        if (lt === "internal" && n.hasProperty("j:linknode"))
          return buildNodeUrl(n.getProperty("j:linknode").getNode() as JCRNodeWrapper);
        if (lt === "external" && n.hasProperty("j:url"))
          return n.getProperty("j:url").getString();
      } catch (_) {}
      return "#";
    };

    const getCtaLabel = (n: JCRNodeWrapper): string => {
      try {
        if (n.hasProperty("ctaLabel")) return n.getProperty("ctaLabel").getString();
      } catch (_) {}
      return "";
    };

    // First button = primary (ticket / inscription), second = secondary (exposer)
    const [ctaPrimaryBtn, ctaSecondaryBtn] = ctaButtons;
    const ctaPrimaryLabel = ctaPrimaryBtn ? getCtaLabel(ctaPrimaryBtn) : props.ctaPrimaryLabel;
    const ctaSecondaryLabel = ctaSecondaryBtn ? getCtaLabel(ctaSecondaryBtn) : props.ctaSecondaryLabel;
    const ctaPrimaryLink = ctaPrimaryBtn ? getCtaHref(ctaPrimaryBtn) : "#";
    const ctaSecondaryLink = ctaSecondaryBtn ? getCtaHref(ctaSecondaryBtn) : "#";

    // Render sibling topBar node if it exists (lives next to the nav node under homePage)
    let topBarNode: JCRNodeWrapper | null = null;
    try {
      if (homePage.hasNode("topbar")) {
        topBarNode = homePage.getNode("topbar") as JCRNodeWrapper;
      }
    } catch (_) {}

    return (
      <header>
        {topBarNode && <Render node={topBarNode} />}
        <div id="header">
          <div className="component header-navigation container-fluid">
            <div className="component-content">
              <div className="grid">
                <a href={logoHref} title="Header-Navigation 1" className="logo" aria-label="Ultimate Supercar Garage">
                  <img src={logoSrc} alt="Ultimate Supercar Garage" />
                </a>

                <div className="title-headline">
                  {props.eventDate && (
                    <span className="field-date">{props.eventDate}</span>
                  )}
                  {props.eventVenue && (
                    <span className="field-lieu">{props.eventVenue}</span>
                  )}
                </div>

                <div className="cta-area">
                  {ctaSecondaryLabel && (
                    <a href={ctaSecondaryLink} className="cta-2">
                      <div>{ctaSecondaryLabel}</div>
                    </a>
                  )}
                  {ctaPrimaryLabel && (
                    <a href={ctaPrimaryLink} className="cta-1">
                      <div>{ctaPrimaryLabel}</div>
                    </a>
                  )}
                </div>

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

                            return (
                              <li
                                key={item.getPath()}
                                className={`item level1${hasL2 ? " submenu" : ""}${isActive ? " active" : ""}`}
                              >
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
                                        <li
                                          key={sub.getPath()}
                                          className={`item level2${hasL3 ? " submenu" : ""}`}
                                        >
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
                                            <ul className={`clearfix ${styles.level3Dropdown}`}>
                                              {level3Items.map((deep: JCRNodeWrapper) => (
                                                <li key={deep.getPath()} className={`item level3 ${styles.level3Item}`}>
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

                          {ctaPrimaryLabel && (
                            <li className="item level1 desktop-hidden">
                              <div className="navigation-title">
                                <a href={ctaPrimaryLink}>{ctaPrimaryLabel}</a>
                              </div>
                            </li>
                          )}
                        </ul>

                        {showLangSwitcher && (
                          <ul aria-label="Language selection" className={styles.langSwitcher}>
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
                                    className={isCurrent ? styles.langLinkActive : styles.langLink}
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

        <script dangerouslySetInnerHTML={{ __html: `(function(){
  var toggle = document.querySelector('[data-mobile-nav-toggle]');
  var navMain = document.querySelector('.navigation-main');
  var nav = document.getElementById('main-nav');
  var mq = window.matchMedia('(max-width: 991.98px)');
  function closeMenu(){
    if (navMain) navMain.classList.remove('is-open');
    document.body.style.overflow = '';
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }
  if (toggle && navMain) {
    toggle.addEventListener('click', function(e) {
      e.stopPropagation();
      var open = navMain.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
      document.body.style.overflow = open ? 'hidden' : '';
    });
  }
  document.querySelectorAll('#main-nav li.level1.submenu > .navigation-title, #main-nav li.level2.submenu > .navigation-title').forEach(function(t) {
    t.addEventListener('click', function(e) {
      if (!mq.matches) return;
      e.preventDefault();
      t.parentElement.classList.toggle('submenu-open');
    });
  });
  if (nav) nav.querySelectorAll('a[href]:not([href="#"])').forEach(function(a) {
    a.addEventListener('click', closeMenu);
  });
  document.addEventListener('click', function(e) {
    if (navMain && navMain.classList.contains('is-open')
        && !navMain.contains(e.target) && (!toggle || !toggle.contains(e.target))) {
      closeMenu();
    }
  });
  mq.addEventListener('change', function(ev) {
    if (!ev.matches) {
      closeMenu();
      document.querySelectorAll('.level1.submenu-open, .level2.submenu-open').forEach(function(x) { x.classList.remove('submenu-open'); });
    }
  });
  var raw = window.location.pathname;
  var jcrPath = raw.replace(/^\\/(?:fr|en)(\\/|$)/, '$1').replace(/\\.html$/, '').replace(/\\/$/, '') || '/';
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
