"use client";

import { useState, useCallback } from "react";
import styles from "./jcrQueryLoadMore.module.css";

interface Props {
  queryId: string;
  pageSize: number;
  total: number;
}

export default function JcrQueryLoadMore({ queryId, pageSize, total }: Props) {
  const [visible, setVisible] = useState(pageSize);

  const handleLoadMore = useCallback(() => {
    setVisible((prev) => {
      const next = prev + pageSize;
      const items = document.querySelectorAll(`[data-qitem="${queryId}"]`);
      items.forEach((el, idx) => {
        if (idx < pageSize) {
          (el as HTMLElement).style.display = "";
          el.setAttribute("data-lm-visible", "true");
        } else if (idx < next) {
          (el as HTMLElement).style.display = "";
          el.setAttribute("data-lm-visible", "true");
        } else {
          (el as HTMLElement).style.display = "none";
          el.setAttribute("data-lm-visible", "false");
        }
      });
      return next;
    });
  }, [pageSize, queryId]);

  const hasMore = visible < total;

  if (!hasMore) return null;

  return (
    <div className={styles.container}>
      <button
        type="button"
        className={styles.button}
        onClick={handleLoadMore}
      >
        Load more
      </button>
      <span className={styles.count}>
        {visible} / {total}
      </span>
    </div>
  );
}
