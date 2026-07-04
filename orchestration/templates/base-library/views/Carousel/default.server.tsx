import {
  getChildNodes,
  jahiaComponent,
  Render,
  RenderChildren,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import styles from "./carousel.module.css";

/**
 * $NS:carousel — slides of any atom (generalized from lsp:heroCarousel).
 * EDIT mode: stacked, every slide rendered as an independent, clickable edit
 * frame via RenderChildren (so each is reachable in Page Builder — G6b).
 * LIVE mode: an auto-advancing carousel (progressive-enhancement JS; the first
 * slide is visible without JS).
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
    const auto = autoplay !== false;
    const intervalMs = interval || 4000;

    return (
      <div className={styles.carousel}>
        <ul className={styles.slides}>
          {children.map((child) => (
            <li key={child.getIdentifier()} className={styles.slide}>
              <Render node={child as JCRNodeWrapper} />
            </li>
          ))}
        </ul>
        {auto && children.length > 1 && (
          <script
            /* progressive enhancement: cycle slides; no-op if JS is off */
            dangerouslySetInnerHTML={{
              __html: `(function(){var r=document.currentScript.parentNode;var s=r.querySelectorAll('.${styles.slide}');if(s.length<=1)return;var c=0;s.forEach(function(e,i){e.style.display=i===0?'':'none';});setInterval(function(){s[c].style.display='none';c=(c+1)%s.length;s[c].style.display='';},${intervalMs});})();`,
            }}
          />
        )}
      </div>
    );
  },
);
