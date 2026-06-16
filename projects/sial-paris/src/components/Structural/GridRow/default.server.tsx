import { jahiaComponent, RenderChildren } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

const gapMap: Record<string, string> = {
  small: "1rem",
  medium: "2rem",
  large: "3rem",
};

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:gridRow",
    displayName: "Grid Row",
  },
  ({ columns = "3", gap = "medium" }: Props) => {
    const cols = parseInt(columns, 10) || 3;
    const gapValue = gapMap[gap] ?? "2rem";

    return (
      <div
        className="grid-row"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: gapValue,
        }}
      >
        <RenderChildren />
      </div>
    );
  },
);
