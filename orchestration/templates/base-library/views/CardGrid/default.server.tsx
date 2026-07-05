import { getChildNodes, jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { Verbatim } from "../Verbatim.js";
import styles from "./cardGrid.module.css";

/**
 * $NS:cardGrid — a grid of $NS:card (generalized from jahiacom-v3
 * cardsCustomerCase / fourArticlesRow). `+ * ($NS:card)`: the editor adds N real
 * cards. RenderChildren filter="$NS:card" renders each through the pipeline and
 * gives the "Add Content" affordance in edit mode (G6b).
 */
function parseColumns(raw: unknown): number {
  const n = Number(raw);
  if (Number.isNaN(n) || n < 2) return 3;
  return Math.min(4, n);
}

jahiaComponent(
  { componentType: "view", nodeType: "$NS:cardGrid", displayName: "Card Grid" },
  (
    {
      heading,
      columns: rawCols,
      skeletonOrig,
    }: { heading?: string; columns?: string; skeletonOrig?: string },
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    // No editorial cards and no heading → verbatim backstop instead of an empty grid.
    const cards = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("$NS:card"),
    );
    if (cards.length === 0 && !heading) return <Verbatim html={skeletonOrig} />;

    const cols = parseColumns(rawCols);
    return (
      <section className={styles.root}>
        {heading && <h2 className={styles.heading}>{heading}</h2>}
        <div
          className={styles.grid}
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        >
          <RenderChildren filter="$NS:card" />
        </div>
      </section>
    );
  },
);
