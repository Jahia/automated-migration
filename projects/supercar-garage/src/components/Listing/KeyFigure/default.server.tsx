import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { KeyFigureProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:keyFigure",
    displayName: "Key Figure",
  },
  ({ value, label, iconClass }: KeyFigureProps) => (
    <div className="col">
      <div>
        <i className={iconClass ?? ""} />
      </div>
      <div className="figure-number">
        <span>{value}</span>
      </div>
      <div className="field-description">{label}</div>
    </div>
  ),
);
