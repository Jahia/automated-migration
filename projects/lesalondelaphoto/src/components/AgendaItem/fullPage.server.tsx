import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import { useTranslation } from "react-i18next";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { AgendaItemProps } from "./types.js";

function resolveImageUrl(image: JCRNodeWrapper | undefined): string | undefined {
  if (!image) return undefined;
  try {
    return buildNodeUrl(image);
  } catch {
    return undefined;
  }
}

function formatDate(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return raw;
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch {
    return raw;
  }
}

function resolveLinkType(node: AgendaItemProps, current: JCRNodeWrapper): string | undefined {
  try {
    if (node["j:linkType"] === "internal" && current.hasProperty("j:linknode")) {
      const linked = current.getProperty("j:linknode").getNode() as JCRNodeWrapper;
      return buildNodeUrl(linked);
    }
    if (node["j:linkType"] === "external" && current.hasProperty("j:url")) {
      return current.getProperty("j:url").getString();
    }
  } catch {
    // no link
  }
  return undefined;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:agendaItem",
    name: "fullPage",
    displayName: "Full Agenda Event",
  },
  (node: AgendaItemProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { t } = useTranslation();
    const title = node["jcr:title"];
    const imageUrl = resolveImageUrl(node.image);
    const altText = node.imageAltText || title || "";
    const dateText = formatDate(node.date);
    const location = node.location;
    const body = node.body;
    const externalLink = resolveLinkType(node, currentNode);

    return (
      <article className="agenda-item-full">
        {imageUrl && (
          <div className="article-hero">
            <img src={imageUrl} alt={altText} className="slide-img" loading="eager" />
          </div>
        )}
        <div className="container-bp p-20">
          {dateText && <div className="article-date">{dateText}</div>}
          {location && <div className="article-location">{location}</div>}
          {title && <h1 className="title-n2">{title}</h1>}
          {body && (
            <div
              className="article-body field-description"
              dangerouslySetInnerHTML={{ __html: body }}
            />
          )}
          {externalLink && (
            <a href={externalLink} className="btn btn-solid-primary mr-20" target="_blank" rel="noopener noreferrer">
              <span>{t("agendaItem.learnMore")}</span>
            </a>
          )}
        </div>
      </article>
    );
  },
);
