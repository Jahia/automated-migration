import {
  Area,
  buildNodeUrl,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Layout } from "../Layout.js";

function pageTitle(n: JCRNodeWrapper): string {
  try {
    if (n.hasProperty("jcr:title")) return n.getProperty("jcr:title").getString();
  } catch (_) {}
  return n.getName();
}

/**
 * Inner page template — mirrors the reference inner-page structure:
 * shared header/nav (Layout) → page banner title → breadcrumb → editable
 * "main" content area → shared footer (Layout). The banner image is the
 * page's own usgmix:pageMedia#bannerImage (editable per page); the breadcrumb
 * is derived from the page hierarchy.
 */
jahiaComponent(
  {
    componentType: "template",
    nodeType: "jnt:page",
    name: "basic",
    displayName: "Basic page",
  },
  ({ "jcr:title": title }: { "jcr:title"?: string }) => {
    const { renderContext } = useServerContext();
    const page = renderContext.getMainResource().getNode() as JCRNodeWrapper;
    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;
    const homePath = homePage.getPath();

    let bannerStyle: { backgroundImage: string } | undefined;
    try {
      if (page.hasProperty("bannerImage")) {
        const img = page.getProperty("bannerImage").getNode() as JCRNodeWrapper;
        bannerStyle = { backgroundImage: `url(${buildNodeUrl(img)})` };
      }
    } catch (_) {}

    const trail: JCRNodeWrapper[] = [];
    let n: JCRNodeWrapper | null = page;
    while (n && n.getPath() !== homePath) {
      if (n.isNodeType("jnt:page")) trail.unshift(n);
      try {
        n = n.getParent() as JCRNodeWrapper;
      } catch (_) {
        n = null;
      }
    }

    return (
      <Layout title={title ?? ""}>
        <div
          className="component title banner-title container text-center text-white col-12"
          style={bannerStyle}
        >
          <div className="component-content">
            <h1>{title ?? pageTitle(page)}</h1>
          </div>
        </div>

        <div className="component breadcrumb navigation-title col-12">
          <div className="component-content">
            <nav aria-label="Fil d'Ariane">
              <ol>
                <li className={`breadcrumb-item home${trail.length === 0 ? " last" : ""}`}>
                  <a href={buildNodeUrl(homePage)}>Accueil</a>
                  {trail.length > 0 && <span className="separator">|</span>}
                </li>
                {trail.map((p: JCRNodeWrapper, i: number) => (
                  <li
                    key={p.getPath()}
                    className={`breadcrumb-item${i === trail.length - 1 ? " last" : ""}`}
                  >
                    <a
                      href={buildNodeUrl(p)}
                      aria-current={i === trail.length - 1 ? "page" : undefined}
                    >
                      {pageTitle(p)}
                    </a>
                    {i < trail.length - 1 && <span className="separator">|</span>}
                  </li>
                ))}
              </ol>
            </nav>
          </div>
        </div>

        <Area name="main" />
      </Layout>
    );
  },
);
