import {
  buildNodeUrl,
  getChildNodes,
  getSiteLocales,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import { useTranslation } from "react-i18next";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { MainNavProps } from "./types.js";
import styles from "./mainNavigation.module.css";

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
    nodeType: "lsp:mainNav",
    displayName: "Navigation principale",
    properties: { "jmix:hiddenType": "true" },
  },
  (props: MainNavProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { t } = useTranslation();
    const { renderContext, currentResource } = useServerContext();
    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;
    const level1Items = getNavItems(homePage);

    let logoUrl: string | undefined;
    try {
      if (props.image) {
        logoUrl = buildNodeUrl(props.image);
      }
    } catch { /* logo not set */ }

    const currentLang = currentResource.getLocale().getLanguage();
    const siteLocales = getSiteLocales();
    const localeEntries = Object.keys(siteLocales);
    const showLangSwitcher = localeEntries.length > 1;

    let ctaUrl: string | undefined;
    let ctaTarget = "";
    try {
      if (currentNode.hasProperty("j:linknode")) {
        const linked = currentNode.getProperty("j:linknode").getNode() as JCRNodeWrapper;
        ctaUrl = buildNodeUrl(linked);
      } else if (currentNode.hasProperty("j:url")) {
        ctaUrl = currentNode.getProperty("j:url").getString();
        ctaTarget = "_blank";
      }
    } catch { /* link not set */ }

    return (
      <>
        <div className="header-navigation container-fluid">
          <div className="grid">
            <a title="Header-Navigation 1" href={buildNodeUrl(homePage)}>
              <div className="logo">
                {logoUrl && (
                  <img
                    src={logoUrl}
                    alt={t("mainNav.siteLogoAlt")}
                    className="img-responsive"
                  />
                )}
              </div>
            </a>

            <div className="title-headline">
              <div className="field-date">{t("mainNav.brandLine1")}</div>
              <div className="field-lieu">{t("mainNav.brandLine2")}</div>
            </div>

            {ctaUrl && (
              <div className="cta-area">
                <a href={ctaUrl} target={ctaTarget}>
                  <div className="cta-1">
                    <i className="fa-solid fa-ticket" />
                    <div className="cta-title-1">{t("mainNav.tickets")}</div>
                  </div>
                </a>
              </div>
            )}

            <div className="hamburger" id="hamburger">
              <span className="line" />
              <span className="line" />
              <span className="line" />
            </div>

            <div className="navigation-main">
              <div className="navigation">
                <div className="component-content">
                  <nav role="navigation" aria-label="Main navigation">
                    <ul className="clearfix">
                      {level1Items.map((item, idx) => {
                        const isMenuText = item.isNodeType("jnt:navMenuText");
                        const level2Items = getNavItems(item);
                        const hasL2 = level2Items.length > 0;
                        const oddEven = idx % 2 === 0 ? "even" : "odd";
                        const firstLast =
                          idx === 0
                            ? "first"
                            : idx === level1Items.length - 1
                              ? "last"
                              : "";

                        return (
                          <li
                            key={item.getPath()}
                            className={`level1${hasL2 ? " submenu" : ""} item${idx} ${oddEven} ${firstLast} rel-level1`}
                          >
                            <i className={item.hasProperty("icon") ? item.getProperty("icon").getString() : ""} />
                            <div className="navigation-title field-navigationtitle">
                              {isMenuText ? (
                                <span className={styles.navLabel}>
                                  {getItemTitle(item)}
                                </span>
                              ) : (
                                <a
                                  title={getItemTitle(item)}
                                  href={getItemUrl(item)}
                                  target=""
                                  data-nav-path={item.getPath()}
                                >
                                  {getItemTitle(item)}
                                </a>
                              )}
                            </div>

                            {hasL2 && (
                              <ul className="clearfix">
                                {level2Items.map((sub, subIdx) => {
                                  const level3Items = getNavItems(sub);
                                  const hasL3 = level3Items.length > 0;
                                  const subOddEven = subIdx % 2 === 0 ? "even" : "odd";
                                  const subFirstLast =
                                    subIdx === 0
                                      ? "first"
                                      : subIdx === level2Items.length - 1
                                        ? "last"
                                        : "";

                                  return (
                                    <li
                                      key={sub.getPath()}
                                      className={`level2 item${subIdx} ${subOddEven} ${subFirstLast} rel-level2${hasL3 ? " submenu" : ""}`}
                                    >
                                      <i className="" />
                                      <div className="navigation-title field-navigationtitle">
                                        <a
                                          title={getItemTitle(sub)}
                                          href={getItemUrl(sub)}
                                          target=""
                                          data-nav-path={sub.getPath()}
                                        >
                                          {getItemTitle(sub)}
                                        </a>
                                      </div>

                                      {hasL3 && (
                                        <ul className="clearfix">
                                          {level3Items.map((deep, deepIdx) => {
                                            const deepOddEven =
                                              deepIdx % 2 === 0 ? "even" : "odd";
                                            const deepFirstLast =
                                              deepIdx === 0
                                                ? "first"
                                                : deepIdx === level3Items.length - 1
                                                  ? "last"
                                                  : "";

                                            return (
                                              <li
                                                key={deep.getPath()}
                                                className={`level3 item${deepIdx} ${deepOddEven} ${deepFirstLast} rel-level3`}
                                              >
                                                <i className="" />
                                                <div className="navigation-title field-navigationtitle">
                                                  <a
                                                    title={getItemTitle(deep)}
                                                    href={getItemUrl(deep)}
                                                    target=""
                                                    data-nav-path={deep.getPath()}
                                                  >
                                                    {getItemTitle(deep)}
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

        {/* Mobile toggle + accordion + active link script */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){
  var hamburger = document.getElementById('hamburger');
  var navMain = document.querySelector('.navigation-main');
  if (!hamburger || !navMain) return;
  hamburger.addEventListener('click', function() {
    var isOpen = navMain.classList.toggle('is-open');
    hamburger.classList.toggle('is-open', isOpen);
    hamburger.setAttribute('aria-expanded', String(isOpen));
  });
  document.addEventListener('click', function(e) {
    if (navMain.classList.contains('is-open')
        && !navMain.contains(e.target) && !hamburger.contains(e.target)) {
      navMain.classList.remove('is-open');
      hamburger.classList.remove('is-open');
      hamburger.setAttribute('aria-expanded', 'false');
    }
  });
  var submenus = document.querySelectorAll('.navigation-main .level1.submenu');
  submenus.forEach(function(item) {
    var title = item.querySelector(':scope > .navigation-title');
    if (!title) return;
    title.addEventListener('click', function() {
      if (window.matchMedia('(max-width: 1199.98px)').matches) {
        item.classList.toggle('submenu-open');
      }
    });
  });
  var raw = window.location.pathname;
  var jcrPath = raw.replace(/^\\/(?:fr|en|es)(\\/|$)/, '$1').replace(/\\.html$/, '').replace(/\\/$/, '') || '/';
  document.querySelectorAll('.navigation-main a[data-nav-path]').forEach(function(link) {
    var navPath = link.getAttribute('data-nav-path');
    if (jcrPath === navPath || jcrPath.startsWith(navPath + '/'))
      link.setAttribute('aria-current', 'page');
  });
})();`,
          }}
        />

        {showLangSwitcher && (
          <style
            dangerouslySetInnerHTML={{
              __html: localeEntries
                .map(
                  (lc) =>
                    `.navigation-main .lang-item-${lc} { display: flex !important; }`
                )
                .join("\n"),
            }}
          />
        )}
      </>
    );
  }
);
