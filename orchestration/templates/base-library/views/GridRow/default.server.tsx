import { AbsoluteArea, jahiaComponent } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import styles from "./gridRow.module.css";
import { useSkeleton } from "../SkeletonBody.js";

/**
 * $NS:gridRow — the LAYOUT PRIMITIVE, transcribed verbatim from the DEPLOYED
 * lsp:gridRow (module-real wins over the spec, MODULARITY-PLAN §5b): a `columns`
 * choice + one AbsoluteArea per column, each an independent open drop zone. This
 * is the tool an editor uses to build N-column layouts without a developer
 * (CLAUDE.md rule 16 — every module ships gridRow).
 */
const MAX_COLS = 4;
const MIN_COLS = 1;
const DEFAULT_COLS = 2;

function parseColumns(raw: unknown): number {
  const n = Number(raw);
  if (Number.isNaN(n) || n < MIN_COLS) return DEFAULT_COLS;
  return Math.min(MAX_COLS, Math.trunc(n));
}

jahiaComponent(
  { componentType: "view", nodeType: "$NS:gridRow", displayName: "Grid Row" },
  ({ columns: rawCols }: { columns?: string }, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    // skeleton-first: a migrated node renders its captured source markup
    const skeletal = useSkeleton();
    if (skeletal) return skeletal;

    const cols = parseColumns(rawCols);
    const indices = Array.from({ length: cols }, (_, i) => i);

    return (
      <section className={styles.root}>
        <div
          className={styles.row}
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        >
          {indices.map((col) => (
            <div key={col} className={styles.col}>
              <AbsoluteArea parent={currentNode} name={`${currentNode.getName()}-col-${col}`} />
            </div>
          ))}
        </div>
      </section>
    );
  },
);
