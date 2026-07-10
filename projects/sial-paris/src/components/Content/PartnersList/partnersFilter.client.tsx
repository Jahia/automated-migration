import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import classes from "./partnersGrid.module.css";

interface Category {
  key: string;
  label: string;
}

/** Client island: category filter tabs that show/hide partner logos by data-category. */
export default function PartnersFilter({
  categories,
  children,
}: {
  categories: Category[];
  children?: ReactNode;
}) {
  const [active, setActive] = useState<string>("all");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.querySelectorAll<HTMLElement>("[data-category]").forEach((el) => {
      el.style.display = active === "all" || el.dataset.category === active ? "" : "none";
    });
  }, [active]);

  return (
    <div>
      <nav className={classes.filters} aria-label="Filtrer les partenaires par catégorie">
        <button
          type="button"
          aria-pressed={active === "all"}
          className={[classes.filterBtn, active === "all" ? classes.active : ""].join(" ").trim()}
          onClick={() => setActive("all")}
        >
          Tous
        </button>
        {categories.map((c) => (
          <button
            key={c.key}
            type="button"
            aria-pressed={active === c.key}
            className={[classes.filterBtn, active === c.key ? classes.active : ""].join(" ").trim()}
            onClick={() => setActive(c.key)}
          >
            {c.label}
          </button>
        ))}
      </nav>
      <div ref={ref}>{children}</div>
    </div>
  );
}
