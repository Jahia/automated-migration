import { useState } from "react";
import { useTranslation } from "react-i18next";
import classes from "./controls.module.css";


export interface CategoryMeta {
  id: string;
  name: string;
}

export interface JcrQueryFilterProps {
  queryId: string;
  categories: CategoryMeta[];
}

export default function JcrQueryFilter({ queryId, categories }: JcrQueryFilterProps) {
  const { t } = useTranslation();
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const applyFilter = (catId: string | null) => {
    setActiveCategory(catId);

    const grid = document.querySelector<HTMLElement>(`[data-qgrid="${queryId}"]`);
    if (!grid) return;

    const items = Array.from(
      grid.querySelectorAll<HTMLElement>(`[data-qitem="${queryId}"]`)
    );

    let matchCount = 0;
    items.forEach((item) => {
      const raw = item.getAttribute("data-categories") ?? "";
      const itemCats = raw ? raw.split(",") : [];
      const visible = !catId || itemCats.includes(catId);
      item.setAttribute("data-cat-visible", visible ? "true" : "false");
      if (visible) matchCount++;
    });

    // Notify LoadMore island: category changed, N items now visible
    grid.dispatchEvent(
      new CustomEvent("qgridfilter", { bubbles: false, detail: { filteredCount: matchCount } })
    );
  };

  if (categories.length === 0) return null;

  return (
    <div className={classes.filterBar} role="group" aria-label={t("jcrQuery.filterLabel")}>
      <button
        type="button"
        className={`${classes.chip} ${activeCategory === null ? classes.chipActive : ""}`}
        onClick={() => applyFilter(null)}
      >
        {t("jcrQuery.filterAll")}
      </button>
      {categories.map((cat) => (
        <button
          key={cat.id}
          type="button"
          className={`${classes.chip} ${activeCategory === cat.id ? classes.chipActive : ""}`}
          onClick={() => applyFilter(cat.id)}
        >
          {cat.name}
        </button>
      ))}
    </div>
  );
}
