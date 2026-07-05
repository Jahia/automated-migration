"use client";

import { Children, type ReactNode, useEffect, useRef, useState } from "react";
import styles from "./carousel.module.css";

/**
 * CarouselIsland — the CLIENT island that re-hydrates prev/next/autoplay/swipe on
 * a carousel whose slides are now COMPOSABLE child nodes (P6.3-bis). It WRAPS the
 * server-rendered slide children (each a real Jahia-pipeline node → its own
 * Page-Builder edit frame in EDIT, G6b), so it is a thin BEHAVIOR layer that never
 * re-renders slide content — it only toggles which wrapper is visible.
 *
 * Generic: advances one slide at a time, wraps around, supports touch swipe +
 * keyboard, over whatever slide count the editor leaves. Replaces the source
 * site's bespoke slider JS (which assumed the source cloned-slide layout that we
 * de-duplicated away), so a re-composed carousel stays interactive.
 */
export function CarouselIsland({
  children,
  autoplay,
  intervalMs,
}: {
  children: ReactNode;
  autoplay: boolean;
  intervalMs: number;
}) {
  const slides = Children.toArray(children);
  const n = slides.length;
  const [idx, setIdx] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const touchX = useRef<number | null>(null);

  const go = (next: number) => setIdx(((next % n) + n) % n);

  useEffect(() => {
    if (!autoplay || n <= 1) return;
    timer.current = setInterval(() => setIdx((i) => (i + 1) % n), intervalMs);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [autoplay, intervalMs, n]);

  if (n === 0) return null;

  return (
    <div
      className={styles.carousel}
      role="region"
      aria-roledescription="carousel"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") go(idx - 1);
        if (e.key === "ArrowRight") go(idx + 1);
      }}
      onTouchStart={(e) => (touchX.current = e.touches[0].clientX)}
      onTouchEnd={(e) => {
        if (touchX.current == null) return;
        const dx = e.changedTouches[0].clientX - touchX.current;
        if (Math.abs(dx) > 40) go(idx + (dx < 0 ? 1 : -1));
        touchX.current = null;
      }}
    >
      <ul className={styles.slides}>
        {slides.map((slide, i) => (
          <li
            key={i}
            className={styles.slide}
            aria-hidden={i !== idx}
            style={{ display: i === idx ? "" : "none" }}
          >
            {slide}
          </li>
        ))}
      </ul>
      {n > 1 && (
        <>
          <button
            type="button"
            className={styles.prev}
            aria-label="Previous slide"
            onClick={() => go(idx - 1)}
          >
            &#8249;
          </button>
          <button
            type="button"
            className={styles.next}
            aria-label="Next slide"
            onClick={() => go(idx + 1)}
          >
            &#8250;
          </button>
          <div className={styles.dots}>
            {slides.map((_, i) => (
              <button
                type="button"
                key={i}
                className={`${styles.dot} ${i === idx ? styles.dotActive : ""}`}
                aria-label={`Go to slide ${i + 1}`}
                aria-current={i === idx}
                onClick={() => go(i)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
