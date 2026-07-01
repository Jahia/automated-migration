import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { KeyFiguresProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:keyFigures",
    displayName: "Key Figures",
  },
  ({ chiffre1, description1, chiffre2, description2, chiffre3, description3, chiffre4, description4 }: KeyFiguresProps) => {
    const figures = [
      { chiffre: chiffre1, description: description1 },
      { chiffre: chiffre2, description: description2 },
      { chiffre: chiffre3, description: description3 },
      { chiffre: chiffre4, description: description4 },
    ].filter((f) => f.chiffre || f.description);

    return (
      <div className="component key-figures col-12">
        <div className="component-content">
          <div className="container-bp">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: `repeat(${Math.min(figures.length, 4)}, minmax(0, 1fr))`,
                gap: "24px",
                textAlign: "center",
              }}
            >
              {figures.map((f, idx) => (
                <div key={idx} className="key-figure-item">
                  {f.chiffre && <div className="field-chiffre key-figure-number">{f.chiffre}</div>}
                  {f.description && <div className="field-description key-figure-desc">{f.description}</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  },
);
