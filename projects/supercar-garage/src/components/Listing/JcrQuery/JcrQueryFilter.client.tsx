"use client";

import { useEffect, useState, useCallback } from "react";
import styles from "./jcrQueryFilter.module.css";

interface FilterChip {
  id: string;
  label: string;
  count: number;
}

interface Props {
  queryId: string;
  chips: FilterChip[];
  activeId: string | null;
}

export default function JcrQueryFilter({ queryId, chips, activeId }: Props) {
  const [selected, setSelected] = useState<string | null>(activeId);

  useEffect(() => {
    const items = document.querySelectorAll(`[data-qitem="${queryId}"]`);
    items.forEach((el) => {
      const elChip = el.getAttribute("data-cat-visible");
      if (selected === null) {
        (el as HTMLElement).style.display = "";
      } else {
        (el as HTMLElement).style.display =
          elChip === selected ? "" : "none";
      }
    });
  }, [selected, queryId]);

  const handleClick = useCallback(
    (id: string) => {
      setSelected((prev) => (prev === id ? null : id));
    },
    [],
  );

  return (
    <div className={styles.chips}>
      {chips.map((chip) => (
        <button
          key={chip.id}
          type="button"
          className={`${styles.chip} ${selected === chip.id ? styles.active : ""}`}
          onClick={() => handleClick(chip.id)}
          aria-pressed={selected === chip.id}
        >
          {chip.label}
          <span className={styles.count}>{chip.count}</span>
        </button>
      ))}
    </div>
  );
}
