import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
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

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:agendaItem",
    name: "default",
    displayName: "Agenda Card",
  },
  (node: AgendaItemProps) => {
    const title = node["jcr:title"];
    const imageUrl = resolveImageUrl(node.image);
    const altText = node.imageAltText || title || "";
    const dateText = formatDate(node.date);
    const location = node.location;

    return (
      <div className="agenda-card">
        {imageUrl && (
          <div className="card-img">
            <img src={imageUrl} alt={altText} className="img-cover" loading="lazy" />
          </div>
        )}
        <div className="card">
          <div className="card-body">
            {dateText && <div className="agenda-date">{dateText}</div>}
            {location && <div className="agenda-location">{location}</div>}
            {title && <h3 className="field-picturegriditemtitre">{title}</h3>}
          </div>
        </div>
      </div>
    );
  },
);
