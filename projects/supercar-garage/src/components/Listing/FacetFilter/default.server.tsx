import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { RenderContext } from "org.jahia.services.render";
import { useTranslation } from "react-i18next";
import type { FacetFilterProps } from "./types.js";
import styles from "./component.module.css";

/**
 * Each entry in `facets` is a pipe-separated string:
 *   "field|label|searchResultsSignature|endpoint"
 * Example: "Themes-Actualites|Themes|allactus|/fr-FR/sxa/search/facets/"
 *
 * Fall back gracefully when any segment is missing.
 */
interface ParsedFacet {
  field: string;
  label: string;
  sig: string;
  endpoint: string;
}

function parseFacet(raw: string): ParsedFacet {
  const parts = raw.split("|");
  return {
    field: parts[0] ?? "",
    label: parts[1] ?? parts[0] ?? "",
    sig: parts[2] ?? "default",
    endpoint: parts[3] ?? "/sxa/search/facets/",
  };
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:facetFilter",
    displayName: "Facet Filter",
  },
  (
    { facets }: FacetFilterProps,
    { renderContext }: { renderContext: RenderContext },
  ) => {
    const { t } = useTranslation();
    const isEdit = renderContext.isEditMode();

    const parsed: ParsedFacet[] = (facets ?? [])
      .filter((f) => typeof f === "string" && f.trim().length > 0)
      .map(parseFacet);

    // Derive search signature from the first facet (all facets on the same bar share one sig).
    const sig = parsed[0]?.sig ?? "default";

    if (isEdit) {
      return (
        <div className={`component facet-aggregated ${styles.editWrapper}`}>
          <div className={styles.editHint}>
            <strong>{t("facetFilter.editHint.title")}</strong>
            <span>{t("facetFilter.editHint.description", { count: parsed.length })}</span>
          </div>
          {parsed.length > 0 && (
            <ul className={styles.editList}>
              {parsed.map((f) => (
                <li key={f.field} className={styles.editItem}>
                  <code>{f.field}</code>
                  {f.label && f.label !== f.field && (
                    <span className={styles.editLabel}> — {f.label}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    }

    return (
      <div className="component facet-aggregated filter-actu col-12 container-bp">
        <div className="component-content">
          {parsed.map((facet) => {
            const dataProps = JSON.stringify({
              endpoint: facet.endpoint,
              f: facet.field,
              searchResultsSignature: facet.sig,
              emptyValueText: "",
              sortOrder: "SortByNames",
            });

            const selectId = `facet-select-${facet.field.toLowerCase().replace(/[^a-z0-9]/g, "-")}`;

            return (
              <div key={facet.field} className="col-md-3">
                <div
                  className={`component facet-dropdown facet-${facet.field.toLowerCase().replace(/[^a-z0-9]/g, "-")} facet-component`}
                  data-properties={dataProps}
                >
                  <div className="component-content">
                    <div className="facet-heading">
                      <h4 className="facet-title">{facet.label}</h4>
                      <span
                        className="clear-filter"
                        role="button"
                        aria-label={t("facetFilter.clearFilter", { label: facet.label })}
                      >
                        x
                      </span>
                    </div>
                    <div>
                      <select
                        className="facet-dropdown-select"
                        id={selectId}
                        name="DropDownOptions"
                        aria-label={facet.label}
                      >
                        <option value="">{facet.label}</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}

          <div className="offset-md-3 col-md-3">
            <div
              className="component facet-summary"
              data-properties={JSON.stringify({ searchResultsSignature: sig })}
            >
              <div className="component-content">
                <div className="facet-heading">
                  <h4 className="facet-title"></h4>
                  <span className="clear-filter" role="button" aria-hidden="true">
                    x
                  </span>
                </div>
                <div className="facet-summary-placeholder"></div>
                <div className="bottom-remove-filter">
                  <button type="button">{t("facetFilter.reset")}</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  },
);
