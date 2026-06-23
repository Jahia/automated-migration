import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import classes from "./controls.module.css";

export interface JcrQueryLoadMoreProps {
  queryId: string;
  pageSize: number;
  total: number;
}


export default function JcrQueryLoadMore({ queryId, pageSize, total }: JcrQueryLoadMoreProps) {
  const { t } = useTranslation();
  const [visibleCount, setVisibleCount] = useState(pageSize);
  const [filteredTotal, setFilteredTotal] = useState(total);

  // Apply load-more visibility to all category-visible items
  const applyLoadMore = (visible: number) => {
    const grid = document.querySelector<HTMLElement>(`[data-qgrid="${queryId}"]`);
    if (!grid) return;

    const items = Array.from(
      grid.querySelectorAll<HTMLElement>(`[data-qitem="${queryId}"]`)
    );

    let shownSoFar = 0;
    items.forEach((item) => {
      // Skip items hidden by the category filter
      if (item.getAttribute("data-cat-visible") === "false") {
        item.setAttribute("data-lm-visible", "false");
        return;
      }
      shownSoFar++;
      item.setAttribute("data-lm-visible", shownSoFar <= visible ? "true" : "false");
    });
  };

  // Initial render: hide items beyond pageSize
  useEffect(() => {
    applyLoadMore(pageSize);
  }, []);

  // Listen for category filter changes - reset visible count
  useEffect(() => {
    const grid = document.querySelector<HTMLElement>(`[data-qgrid="${queryId}"]`);
    if (!grid) return;

    const onFilter = (e: Event) => {
      const { filteredCount } = (e as CustomEvent<{ filteredCount: number }>).detail;
      setFilteredTotal(filteredCount);
      setVisibleCount(pageSize);
      applyLoadMore(pageSize);
    };

    grid.addEventListener("qgridfilter", onFilter);
    return () => grid.removeEventListener("qgridfilter", onFilter);
  }, [queryId, pageSize]);

  // Re-apply whenever visibleCount changes (load more click)
  useEffect(() => {
    applyLoadMore(visibleCount);
  }, [visibleCount]);

  const handleLoadMore = () => {
    setVisibleCount((prev) => prev + pageSize);
  };

  const remaining = filteredTotal - visibleCount;
  if (remaining <= 0) return null;

  return (
    <div className={classes.loadMoreWrapper}>
      <button
        type="button"
        className={classes.loadMoreBtn}
        onClick={handleLoadMore}
      >
        {t("jcrQuery.loadMore")}
        <span className={classes.loadMoreCount}>
          {t("jcrQuery.loadMoreCount", { count: Math.min(pageSize, remaining) })}
        </span>
      </button>
    </div>
  );
}
