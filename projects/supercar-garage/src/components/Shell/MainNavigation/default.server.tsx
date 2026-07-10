import {
  buildModuleFileUrl,
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { MainNavigationProps } from "./types.js";

// Pages excluded from main nav (they appear in the TopBar instead)
const NAV_EXCLUDED = new Set(["espace-exposant", "presse"]);

const getNavItems = (node: JCRNodeWrapper, isHome = false): JCRNodeWrapper[] =>
  getChildNodes(node, -1, 0, (n: JCRNodeWrapper) => {
    if (!n.isNodeType("jnt:page")) return false;
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

const parity = (i: number) => (i % 2 === 0 ? "odd" : "even");

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:mainNavigation",
    displayName: "Main Navigation",
  },
  (props: MainNavigationProps, { currentNode }) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();

    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;
    const mainNode = renderContext.getMainResource().getNode() as JCRNodeWrapper;
    const level1Items = getNavItems(homePage, true);

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

    // First child = primary (cta-1: ticket / inscription, right),
    // second child = secondary (cta-2: store / exposer, left).
    const [ctaPrimaryBtn, ctaSecondaryBtn] = ctaButtons;
    const ctaPrimaryLabel = ctaPrimaryBtn ? getCtaLabel(ctaPrimaryBtn) : props.ctaPrimaryLabel;
    const ctaSecondaryLabel = ctaSecondaryBtn ? getCtaLabel(ctaSecondaryBtn) : props.ctaSecondaryLabel;
    const ctaPrimaryLink = ctaPrimaryBtn ? getCtaHref(ctaPrimaryBtn) : "#";
    const ctaSecondaryLink = ctaSecondaryBtn ? getCtaHref(ctaSecondaryBtn) : "#";

    // topBar is its own AbsoluteArea in Layout.tsx (independently editable, and
    // it holds the social links + language selector), so it is NOT rendered here.
    return (
      <header>
        <div id="header">
          <div className="component header-navigation container-fluid">
            <div className="component-content">
              <div className="grid">
                <a href={logoHref} title="Header-Navigation 1" aria-label="Ultimate Supercar Garage">
                  <div className="logo">
                    <img className="img-responsive" src={logoSrc} alt="Ultimate Supercar Garage" />
                  </div>
                </a>

                <div className="title-headline">
                  {props.eventDate && <div className="field-date">{props.eventDate}</div>}
                  {props.eventVenue && <div className="field-lieu">{props.eventVenue}</div>}
                </div>

                <div className="cta-area">
                  {ctaSecondaryLabel && (
                    <a href={ctaSecondaryLink} title={ctaSecondaryLabel}>
                      <div className="cta-2">
                        <i className="fa-solid fa-store" aria-hidden="true"></i>
                        <div className="field-cta-title-2">{ctaSecondaryLabel}</div>
                      </div>
                    </a>
                  )}
                  {ctaPrimaryLabel && (
                    <a href={ctaPrimaryLink} title={ctaPrimaryLabel}>
                      <div className="cta-1">
                        <i className="fa-solid fa-ticket" aria-hidden="true"></i>
                        <div className="field-cta-title-1">{ctaPrimaryLabel}</div>
                      </div>
                    </a>
                  )}
                </div>

                <div className="component plain-html height0">
                  <div className="component-content">
                    <div
                      className="hamburger"
                      id="hamburger"
                      role="button"
                      tabIndex={0}
                      aria-label="Menu"
                      aria-expanded="false"
                      aria-controls="main-nav"
                    >
                      <span className="line"></span>
                      <span className="line"></span>
                      <span className="line"></span>
                    </div>
                  </div>
                </div>

                <div className="navigation-main">
                  <div className="component navigation">
                    <div className="component-content">
                      <nav id="main-nav" aria-label="Navigation principale">
                        <ul className="clearfix">
                          {level1Items.map((item: JCRNodeWrapper, i: number) => {
                            const level2Items = isEdit ? [] : getNavItems(item);
                            const hasL2 = level2Items.length > 0;
                            const isActive =
                              item.isNodeType("jnt:page") &&
                              (item.getPath() === mainNode.getPath() ||
                                mainNode.getPath().startsWith(item.getPath() + "/"));
                            const cls = [
                              "level1",
                              hasL2 ? "submenu" : "",
                              `item${i}`,
                              parity(i),
                              i === 0 ? "first" : "",
                              i === level1Items.length - 1 ? "last" : "",
                              "rel-level1",
                              isActive ? "active" : "",
                            ]
                              .filter(Boolean)
                              .join(" ");

                            return (
                              <li key={item.getPath()} className={cls}>
                                <i className="" aria-hidden="true"></i>
                                <div className="navigation-title field-navigationtitle">
                                  <a
                                    href={getItemUrl(item)}
                                    title={getItemTitle(item)}
                                    data-nav-path={item.getPath()}
                                    aria-current={isActive ? "page" : undefined}
                                  >
                                    {getItemTitle(item)}
                                  </a>
                                </div>
                                {hasL2 && (
                                  <ul className="clearfix">
                                    {/* mobile-only duplicate of the parent link */}
                                    <li className="desktop-hidden level2 item0 odd first rel-level2">
                                      <i className="" aria-hidden="true"></i>
                                      <div className="navigation-title field-navigationtitle">
                                        <a href={getItemUrl(item)}>{getItemTitle(item)}</a>
                                      </div>
                                    </li>
                                    {level2Items.map((sub: JCRNodeWrapper, j: number) => {
                                      const k = j + 1;
                                      const subCls = [
                                        "level2",
                                        `item${k}`,
                                        parity(k),
                                        j === level2Items.length - 1 ? "last" : "",
                                        "rel-level2",
                                      ]
                                        .filter(Boolean)
                                        .join(" ");
                                      return (
                                        <li key={sub.getPath()} className={subCls}>
                                          <i className="" aria-hidden="true"></i>
                                          <div className="navigation-title field-navigationtitle">
                                            <a href={getItemUrl(sub)} data-nav-path={sub.getPath()}>
                                              {getItemTitle(sub)}
                                            </a>
                                          </div>
                                        </li>
                                      );
                                    })}
                                  </ul>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      </nav>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <script dangerouslySetInnerHTML={{ __html: `(function(){
  var toggle = document.getElementById('hamburger');
  var navMain = document.querySelector('.navigation-main');
  var nav = document.getElementById('main-nav');
  var headerEl = document.getElementById('header');
  var mq = window.matchMedia('(max-width: 991.98px)');
  function closeMenu(){
    if (navMain) navMain.classList.remove('is-open');
    if (headerEl) headerEl.classList.remove('nav-open');
    document.body.style.overflow = '';
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }
  if (toggle && navMain) {
    toggle.addEventListener('click', function(e) {
      e.stopPropagation();
      var open = navMain.classList.toggle('is-open');
      if (headerEl) headerEl.classList.toggle('nav-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      document.body.style.overflow = open ? 'hidden' : '';
    });
  }
  document.querySelectorAll('#main-nav li.level1.submenu > .navigation-title').forEach(function(t) {
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
      document.querySelectorAll('.level1.submenu-open').forEach(function(x) { x.classList.remove('submenu-open'); });
    }
  });
  // Toggle #header.is-sticky once the social top-bar has scrolled away
  var topbar = document.querySelector('.top-navbar');
  function onScroll(){
    var threshold = topbar ? topbar.offsetHeight : 32;
    if (headerEl) headerEl.classList.toggle('is-sticky', window.scrollY > threshold);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
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
