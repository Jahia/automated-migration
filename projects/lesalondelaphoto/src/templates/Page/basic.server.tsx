import { Area, buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.js";

// Standard section page: an OPEN composition surface — gridRow (layout) + body content
// components. "Structured by components only": the contributor builds the page from the
// palette; no fixed slots. Children/shell/mainResource types stay excluded.
const OPEN_PALETTE = [
  "lsp:gridRow",
  "lsp:editorialBlock",
  "lsp:cardGrid",
  "lsp:promoBlock",
  "lsp:partnerCarousel",
  "lsp:jcrQuery",
  "lsp:externalEmbed",
  "lsp:keyFigures",
  "lsp:accordion",
  "lsp:tabs",
  "lsp:contactBlock",
  "lsp:dateLieuHoraires",
  "lsp:infoCard",
  "lsp:imageBlock",
  "lsp:anchorsLinks",
  "lsp:pageHeader",
];

/** Walk from currentNode up to home page, returning an ordered array of ancestor jnt:page nodes (home first, current last). */
function getBreadcrumbPath(currentNode: JCRNodeWrapper): JCRNodeWrapper[] {
  const chain: JCRNodeWrapper[] = [currentNode];
  let cursor = currentNode;
  let depth = cursor.getPath().split("/").length;
  while (depth > 2) {
    try {
      const parent = cursor.getParent() as unknown as JCRNodeWrapper;
      if (parent.isNodeType("jnt:page")) {
        chain.unshift(parent);
      }
      cursor = parent;
      depth = cursor.getPath().split("/").length;
    } catch {
      break;
    }
  }
  return chain;
}

/** Safely read jcr:title from a page node, falling back to its system name. */
function getPageTitle(node: JCRNodeWrapper): string {
  try {
    if (node.hasProperty("jcr:title")) return node.getProperty("jcr:title").getString();
  } catch { /* missing */ }
  return node.getName();
}

jahiaComponent(
  { componentType: "template", nodeType: "jnt:page", name: "basic", displayName: "Basic page" },
  ({ "jcr:title": title }: { "jcr:title"?: string }, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const breadcrumb = getBreadcrumbPath(currentNode);
    const isHome = breadcrumb.length <= 1;

    return (
      <Layout title={title || getPageTitle(currentNode)}>
        {/* Page banner title — contributes the semantic page heading */}
        <div className="component page-header col-12">
          <div className="component-content">
            <div className="container-bp p-20 mb-20">
              <h1 className="field-titre title-n1">{title || getPageTitle(currentNode)}</h1>
            </div>
          </div>
        </div>

        {/* Breadcrumb — skipped on the home page (no ancestor pages) */}
        {!isHome && (
          <div id="content-breadcrumb">
            <div className="row">
              <div className="breadcrumb">
                <div className="component-content">
                  {breadcrumb.map((page, idx) => {
                    const isLast = idx === breadcrumb.length - 1;
                    return (
                      <div key={page.getPath()} className={`breadcrumb-item${isLast ? " last" : ""}`}>
                        <div className="navigation-title">
                          <a href={buildNodeUrl(page)}>{getPageTitle(page)}</a>
                        </div>
                        {!isLast && <span className="separator">&gt;</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        <Area name="main" allowedNodeTypes={OPEN_PALETTE} />
      </Layout>
    );
  },
);
