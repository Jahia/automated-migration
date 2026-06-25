import {
  buildNodeUrl,
  getChildNodes,
  getSiteLocales,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { TopBarProps } from "./types.js";

const getSocialHref = (node: JCRNodeWrapper): string => {
  try {
    const linkType = node.hasProperty("j:linkType")
      ? node.getProperty("j:linkType").getString()
      : "none";
    if (linkType === "internal" && node.hasProperty("j:linknode")) {
      return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
    }
    if (linkType === "external" && node.hasProperty("j:url")) {
      return node.getProperty("j:url").getString();
    }
  } catch (_) {}
  return "#";
};

const getCtaHref = (node: JCRNodeWrapper): string => {
  try {
    const linkType = node.hasProperty("j:linkType")
      ? node.getProperty("j:linkType").getString()
      : "none";
    if (linkType === "internal" && node.hasProperty("j:linknode")) {
      return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
    }
    if (linkType === "external" && node.hasProperty("j:url")) {
      return node.getProperty("j:url").getString();
    }
  } catch (_) {}
  return "#";
};

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:topBar",
    displayName: "Top Bar",
  },
  (props: TopBarProps, { currentNode }) => {
    const { renderContext, currentResource } = useServerContext();

    const currentLang = currentResource.getLocale().getLanguage();
    const siteLocales = getSiteLocales();
    const showLangSwitcher = Object.keys(siteLocales).length > 1;

    const socialLinks = getChildNodes(
      currentNode,
      -1,
      0,
      (n: JCRNodeWrapper) => n.isNodeType("usg:socialLink"),
    );

    const ctaButtons = getChildNodes(
      currentNode,
      -1,
      0,
      (n: JCRNodeWrapper) => n.isNodeType("usg:ctaButton"),
    );

    const [ctaExposer, ctaPresse] = ctaButtons;

    const exposerLabel = props.ctaExposerLabel;
    const presseLabel = props.ctaPresseLabel;
    const exposerHref = ctaExposer ? getCtaHref(ctaExposer) : "#";
    const presseHref = ctaPresse ? getCtaHref(ctaPresse) : "#";

    const mainNode = renderContext.getMainResource().getNode() as JCRNodeWrapper;

    return (
      <div className="component top-bar top-navbar container-fluid">
        <div className="component-content">
          <div className="row align-items-center parent-row">

            {/* Social links - hidden on mobile */}
            <div className="d-md-down-none socials">
              {socialLinks.map((social: JCRNodeWrapper) => {
                const iconClass = social.hasProperty("iconClass")
                  ? social.getProperty("iconClass").getString()
                  : "";
                const href = getSocialHref(social);
                const platform = social.hasProperty("platform")
                  ? social.getProperty("platform").getString()
                  : "";
                return (
                  <a
                    key={social.getPath()}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    href={href}
                    aria-label={platform}
                  >
                    <div>
                      {iconClass && <i className={iconClass}></i>}
                    </div>
                  </a>
                );
              })}
            </div>

            {/* CTA buttons - hidden on mobile */}
            <div className="col-auto">
              {exposerLabel && (
                <a title="" href={exposerHref} target="">
                  <div className="call-back">
                    <i className="fa-regular fa-store"></i>
                    <div className="field-texte-1">{exposerLabel}</div>
                  </div>
                </a>
              )}
              {presseLabel && (
                <a title="" href={presseHref} target="">
                  <div className="d-md-down-none">
                    <i className="fa-regular fa-microphone-stand"></i>
                    <div className="field-texte-2">{presseLabel}</div>
                  </div>
                </a>
              )}
            </div>

            {/* Language selector + search */}
            <div className="d-flex">
              <a title="" href="" target="">
                <div className="search">
                  <i className=""></i>
                </div>
              </a>

              {showLangSwitcher && (
                <div className="component language-selector">
                  <div className="component-content">
                    <div
                      className="language-selector-select-item"
                      data-language-code={currentLang}
                    >
                      <a className="language-selector-select-link">
                        {currentLang.toUpperCase()}
                      </a>
                    </div>
                    <ul className="language-selector-item-container">
                      {Object.keys(siteLocales).map((langCode) => {
                        const isCurrent = langCode === currentLang;
                        const url = buildNodeUrl(mainNode, { language: langCode });
                        return (
                          <li
                            key={langCode}
                            className={`language-selector-item${isCurrent ? " is-active" : ""}`}
                            data-language-code={langCode}
                          >
                            <a href={url} lang={langCode} hrefLang={langCode}>
                              {langCode.toUpperCase()}
                            </a>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                </div>
              )}
            </div>

          </div>
        </div>
      </div>
    );
  },
);
