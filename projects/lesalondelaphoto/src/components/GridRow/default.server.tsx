import { AbsoluteArea, jahiaComponent } from "@jahia/javascript-modules-library";
import type { GridRowProps } from "./types.js";
import styles from "./gridRow.module.css";

const MAX_COLS = 4;
const MIN_COLS = 1;
const DEFAULT_COLS = 2;

function parseColumns(raw: unknown): number {
  const n = Number(raw);
  if (Number.isNaN(n) || n < MIN_COLS) return DEFAULT_COLS;
  return Math.min(MAX_COLS, Math.trunc(n));
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:gridRow",
    displayName: "Grid Row",
  },
  ({ columns: rawCols }: GridRowProps, { currentNode }) => {
    const cols = parseColumns(rawCols);
    const areaNames = Array.from({ length: cols }, (_, index) => index);

    return (
      <section className={styles.root}>
        <div
          className={styles.row}
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        >
          {areaNames.map((col) => (
            <div key={col} className={styles.col}>
              <AbsoluteArea parent={currentNode} name={`${currentNode.getName()}-col-${col}`} />
            </div>
          ))}
        </div>
      </section>
    );
  },
);
