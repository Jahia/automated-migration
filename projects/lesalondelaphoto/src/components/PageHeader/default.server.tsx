import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { PageHeaderProps } from "./types.js";

function formatDate(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:pageHeader",
    displayName: "Page Header",
  },
  ({ titre, sousTitre, arriereTitre, datePublication }: PageHeaderProps) => {
    const formattedDate = formatDate(datePublication);

    return (
      <div className="component page-header col-12">
        <div className="component-content">
          <div className="container-bp p-20 mb-20">
            {arriereTitre && (
              <div className="field-arriere-titre page-header-eyebrow">
                {arriereTitre}
              </div>
            )}
            {titre && <h1 className="field-titre title-n1">{titre}</h1>}
            {sousTitre && (
              <div className="field-sous-titre page-header-subtitle">
                {sousTitre}
              </div>
            )}
            {formattedDate && (
              <div className="field-date-de-publication page-header-date">
                {formattedDate}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  },
);
