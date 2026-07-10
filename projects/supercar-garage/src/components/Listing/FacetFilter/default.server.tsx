import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { RenderContext } from "org.jahia.services.render";
import { useTranslation } from "react-i18next";
import type { FacetFilterProps } from "./types.js";
import styles from "./component.module.css";

/**
 * Each entry in `facets` is a pipe-separated string: "field|label|...".
 * The field name decides which card attribute this dropdown filters:
 *   contains "theme" → data-theme,  contains "type" → data-type.
 * The dropdowns are populated client-side from the rendered news cards'
 * `data-theme` / `data-type` attributes (set by the newsArticle card view),
 * and filtering is a client-side show/hide of `.search-result-item` cards.
 * This replaces the old SXA search facets, which had no backend in Jahia.
 */
interface ParsedFacet {
  field: string;
  label: string;
  attr: string;
}

function parseFacet(raw: string): ParsedFacet {
  const parts = raw.split("|");
  const field = parts[0] ?? "";
  const label = parts[1] ?? field;
  const lower = field.toLowerCase();
  const attr = lower.includes("theme")
    ? "data-theme"
    : lower.includes("type")
      ? "data-type"
      : `data-${lower.replace(/[^a-z0-9]/g, "-")}`;
  return { field, label, attr };
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
                  <span className={styles.editLabel}> → filtre par {f.attr}</span>
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
            const selectId = `facet-${facet.attr}`;
            return (
              <div key={facet.field} className="col-md-3 facet-dropdown">
                <div className="facet-heading">
                  <h4 className="facet-title">{facet.label}</h4>
                </div>
                <select
                  className="facet-dropdown-select"
                  id={selectId}
                  data-filter-attr={facet.attr}
                  aria-label={facet.label}
                >
                  <option value="">{facet.label}</option>
                </select>
              </div>
            );
          })}

          <div className="col-md-3 facet-reset">
            <button type="button" className="facet-reset-btn">
              {t("facetFilter.reset")}
            </button>
          </div>
        </div>

        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){
  function init(){
    var selects = [].slice.call(document.querySelectorAll('.filter-actu select[data-filter-attr]'));
    if(!selects.length) return;
    var cards = [].slice.call(document.querySelectorAll('.search-result-item'));
    if(!cards.length){ setTimeout(init,300); return; }
    selects.forEach(function(sel){
      if(sel.options.length>1) return; // already populated
      var attr = sel.getAttribute('data-filter-attr');
      var labelSel = attr === 'data-theme' ? '.label-theme' : '.label-type';
      var map = {};
      cards.forEach(function(c){
        var v = c.getAttribute(attr); if(!v) return;
        var el = c.querySelector(labelSel);
        var lbl = (el && el.textContent.trim()) || v;
        if(!map[v]) map[v] = { label: lbl, count: 0 };
        map[v].count++;
      });
      Object.keys(map).sort().forEach(function(k){
        var o = document.createElement('option');
        o.value = k; o.textContent = map[k].label + ' (' + map[k].count + ')';
        sel.appendChild(o);
      });
    });
    function apply(){
      cards.forEach(function(c){
        var show = selects.every(function(sel){
          var v = sel.value; if(!v) return true;
          return c.getAttribute(sel.getAttribute('data-filter-attr')) === v;
        });
        c.style.display = show ? '' : 'none';
      });
    }
    selects.forEach(function(sel){ sel.addEventListener('change', apply); });
    var reset = document.querySelector('.filter-actu .facet-reset-btn');
    if(reset) reset.addEventListener('click', function(){ selects.forEach(function(s){ s.value=''; }); apply(); });
  }
  if(document.readyState!=='loading') init(); else document.addEventListener('DOMContentLoaded', init);
})();`,
          }}
        />
      </div>
    );
  },
);
