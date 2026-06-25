import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { useTranslation } from "react-i18next";
import type { PressReleaseProps } from "./types.js";

/**
 * Full-page detail view for a single press release, rendered when the press
 * release is requested at its own URL via the MainResource template. Renders
 * ONLY the press-release body — the shared header/footer come from Layout in
 * the MainResource template wrapper. Never add Layout or AbsoluteArea here.
 */
jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:pressRelease",
    name: "fullPage",
    displayName: "Press Release — Full Page",
  },
  (
    { "jcr:title": title, publishDate, image, summary, bodyContent, pressContact }: PressReleaseProps,
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const { t } = useTranslation();
    const imageSrc = image ? buildNodeUrl(image) : undefined;

    let formattedDate: string | undefined;
    if (publishDate) {
      try {
        formattedDate = new Date(publishDate).toLocaleDateString(undefined, {
          year: "numeric",
          month: "long",
          day: "numeric",
        });
      } catch (_) {
        formattedDate = publishDate;
      }
    }

    const tags: string[] = [];
    try {
      if (currentNode.hasProperty("j:tagList")) {
        const tagValues = currentNode.getProperty("j:tagList").getValues();
        for (let i = 0; i < tagValues.length; i++) {
          tags.push(tagValues[i].getString());
        }
      }
    } catch (_) {
      // no tags
    }

    return (
      <article className="content col-12">
        <div className="component-content">
          <div className="container-bp">
            <header className="section-header">
              <div className="labels">
                <span className="label-type">{t("pressRelease.badge")}</span>
                {tags.map((tag) => (
                  <span key={tag} className="label-theme">
                    {tag}
                  </span>
                ))}
              </div>

              {title && <h1 className="field-title">{title}</h1>}

              {formattedDate && (
                <time className="text-muted" dateTime={publishDate}>
                  {formattedDate}
                </time>
              )}

              {pressContact && <p className="text-muted">{pressContact}</p>}
            </header>

            {imageSrc && (
              <figure className="content-block-vertical-image">
                <img src={imageSrc} alt={title ?? ""} />
              </figure>
            )}

            {summary && (
              <div
                className="field-description rich-text"
                dangerouslySetInnerHTML={{ __html: summary }}
              />
            )}

            {bodyContent && (
              <div
                className="field-content rich-text"
                dangerouslySetInnerHTML={{ __html: bodyContent }}
              />
            )}
          </div>
        </div>
      </article>
    );
  },
);
