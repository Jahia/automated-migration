import {
  getChildNodes,
  jahiaComponent,
  Render,
  RenderChildren,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
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
    { autoplay, interval }: { autoplay?: boolean; interval?: number },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const { renderContext } = useServerContext();

    if (renderContext.isEditMode()) {
      return (
        <div className={styles.editStack}>
          <RenderChildren />
        </div>
      );
    }

    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("$NSMIX:component"),
    );

    return (
      <CarouselIsland autoplay={autoplay !== false} intervalMs={interval || 5000}>
        {children.map((child) => (
          <Render key={child.getIdentifier()} node={child as JCRNodeWrapper} />
        ))}
      </CarouselIsland>
    );
  },
);
