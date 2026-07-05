import {
  getChildNodes,
  jahiaComponent,
  Render,
  RenderChildren,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Verbatim } from "../Verbatim.js";
import { useSkeleton } from "../SkeletonBody.js";
import { CarouselIsland } from "./CarouselIsland.client.js";
import styles from "./carousel.module.css";

/**
 * $NS:carousel — slides of any atom (P6.3-bis: promoted from a JS slider/carousel
 * with cloned-slide dedup). The recognizer de-duplicates the source's cloned
 * infinite-scroll slides so the child nodes are the CANONICAL slides only.
 *
 * EDIT mode: stacked, every slide rendered as an independent, clickable edit frame
 * via RenderChildren (each slide reachable in Page Builder — G6b).
 * LIVE mode: a CLIENT ISLAND (CarouselIsland) re-hydrates prev/next/autoplay/swipe
 * on the composable slide children — the source site's bespoke slider JS is
 * replaced (it assumed the cloned layout), so a re-composed carousel stays
 * interactive. The first slide is visible before hydration (progressive enhancement).
 */
jahiaComponent(
  { componentType: "view", nodeType: "$NS:carousel", displayName: "Carousel" },
  (
    {
      autoplay,
      interval,
      skeleton,
      skeletonOrig,
    }: { autoplay?: boolean; interval?: number; skeleton?: string; skeletonOrig?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;

    const { renderContext } = useServerContext();

    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("$NSMIX:component"),
    );

    // No editorial slides → verbatim backstop instead of an empty carousel shell.
    if (children.length === 0) return <Verbatim html={skeleton ?? skeletonOrig} />;

    if (renderContext.isEditMode()) {
      return (
        <div className={styles.editStack}>
          <RenderChildren />
        </div>
      );
    }

    return (
      <CarouselIsland autoplay={autoplay !== false} intervalMs={interval || 5000}>
        {children.map((child) => (
          <Render key={child.getIdentifier()} node={child as JCRNodeWrapper} />
        ))}
      </CarouselIsland>
    );
  },
);
