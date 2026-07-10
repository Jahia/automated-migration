import { buildNodeUrl, jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { useTranslation } from "react-i18next";
import type { BreadcrumbProps } from "./types.js";

/**
 * Build the ancestor chain from the site home page down to (and including) the current page.
 * Returns an empty array if the current node is the home page itself.
 */
function buildTrail(
  homePath: string,
  currentNode: JCRNodeWrapper,
): JCRNodeWrapper[] {
  const trail: JCRNodeWrapper[] = [];
  let node: JCRNodeWrapper = currentNode;

  // Walk up until we reach the home page (inclusive) or the site root
  while (node && node.getPath() !== homePath) {
    if (node.isNodeType("jnt:page")) {
      trail.unshift(node);
    }
    try {
      node = node.getParent() as JCRNodeWrapper;
    } catch (_) {
      break;
    }
  }

  return trail;
}

function getPageTitle(node: JCRNodeWrapper): string {
  try {
    if (node.hasProperty("jcr:title")) return node.getProperty("jcr:title").getString();
  } catch (_) {}
  return node.getName();
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:breadcrumb",
    displayName: "Breadcrumb",
  },
  (_props: BreadcrumbProps) => {
    const { t } = useTranslation();
    const { renderContext } = useServerContext();

    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;
    const mainNode = renderContext.getMainResource().getNode() as JCRNodeWrapper;

    // The breadcrumb renders relative to the current page (mainNode),
    // not relative to the component node itself.
    const trail = buildTrail(homePage.getPath(), mainNode);

    return (
      <div className="component breadcrumb navigation-title col-12">
        <div className="component-content">
          <nav aria-label={t("breadcrumb.ariaLabel")}>
            <ol>
              {/* Home item — always first */}
              <li className={`breadcrumb-item home${trail.length === 0 ? " last" : ""}`}>
                <div className="navigation-title field-navigationtitle">
                  <a title="Home" href={buildNodeUrl(homePage)}>
                    {t("breadcrumb.home")}
                  </a>
                </div>
                <span className="separator">|</span>
              </li>

              {/* Interior pages: each ancestor page then the current page */}
              {trail.map((page: JCRNodeWrapper, index: number) => {
                const isLast = index === trail.length - 1;
                return (
                  <li
                    key={page.getPath()}
                    className={`breadcrumb-item${isLast ? " last" : ""}`}
                  >
                    <div className="navigation-title field-navigationtitle">
                      <a
                        title={page.getName()}
                        href={buildNodeUrl(page)}
                        aria-current={isLast ? "page" : undefined}
                      >
                        {getPageTitle(page)}
                      </a>
                    </div>
                    <span className="separator">|</span>
                  </li>
                );
              })}
            </ol>
          </nav>
        </div>
      </div>
    );
  },
);
