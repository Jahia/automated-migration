import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { DateLieuHorairesProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:dateLieuHoraires",
    displayName: "Date Lieu Horaires",
  },
  ({ titre1, description1, titre2, description2, titre3, description3 }: DateLieuHorairesProps) => {
    const blocks = [
      { titre: titre1, description: description1 },
      { titre: titre2, description: description2 },
      { titre: titre3, description: description3 },
    ].filter((b) => b.titre);

    return (
      <div className="component date-lieu-horaires col-12">
        <div className="component-content">
          <div className="container-bp">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: `repeat(${Math.min(blocks.length, 3)}, minmax(0, 1fr))`,
                gap: "32px",
              }}
            >
              {blocks.map((b, idx) => (
                <div key={idx} className="dlh-block">
                  <div className="dlh-icon">
                    <i className={`fa-solid ${idx === 0 ? "fa-calendar-days" : idx === 1 ? "fa-location-dot" : "fa-clock"}`} />
                  </div>
                  <h3 className="field-titre dlh-title">{b.titre}</h3>
                  {b.description && (
                    <div className="field-description dlh-desc" dangerouslySetInnerHTML={{ __html: b.description }} />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  },
);
