import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { useTranslation } from "react-i18next";
import type { SectionHubProps } from "./types.js";

function getPageTitle(page: JCRNodeWrapper): string {
  try {
    if (page.hasProperty("jcr:title")) return page.getProperty("jcr:title").getString();
  } catch (_) {}
  return page.getName();
}

function getPageDescription(page: JCRNodeWrapper): string | null {
  try {
    if (page.hasProperty("description")) return page.getProperty("description").getString();
    if (page.hasProperty("j:description")) return page.getProperty("j:description").getString();
    if (page.hasProperty("jcr:description")) return page.getProperty("jcr:description").getString();
  } catch (_) {}
  return null;
}

function getPageImageUrl(page: JCRNodeWrapper): string | null {
  try {
    if (page.hasProperty("bannerImage")) {
      const imageNode = page.getProperty("bannerImage").getNode() as JCRNodeWrapper;
      return buildNodeUrl(imageNode);
    }
    if (page.hasProperty("thumbnailImage")) {
      const imageNode = page.getProperty("thumbnailImage").getNode() as JCRNodeWrapper;
      return buildNodeUrl(imageNode);
    }
  } catch (_) {}
  return null;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:sectionHub",
    displayName: "Section Hub",
  },
  ({ childPages }: SectionHubProps) => {
    const { t } = useTranslation();
    const pages = childPages?.filter((p) => p != null) ?? [];

    if (pages.length === 0) return null;

    return (
      <div className="component page-list  level-2 col-12">
        <div className="component-content">
          <ul className="items">
            {pages.map((page: JCRNodeWrapper) => {
              const title = getPageTitle(page);
              const description = getPageDescription(page);
              const imageUrl = getPageImageUrl(page);
              let pageUrl = "#";
              try {
                pageUrl = buildNodeUrl(page);
              } catch (_) {}

              return (
                <li key={page.getPath()} className="item">
                  {imageUrl && (
                    <img
                      src={imageUrl}
                      alt={title}
                      className="img-cover"
                      loading="lazy"
                    />
                  )}
                  <div className="card">
                    {title && imageUrl && (
                      <h2 className="field-title">{title}</h2>
                    )}
                    {description && (
                      <div
                        className="field-content"
                        dangerouslySetInnerHTML={{ __html: description }}
                      />
                    )}
                    <a title={page.getName()} href={pageUrl}>
                      <div className="btn btn-primary">
                        <span>{t("sectionHub.readMore")}</span>
                      </div>
                    </a>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    );
  },
);
