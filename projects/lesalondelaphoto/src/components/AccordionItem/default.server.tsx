import { jahiaComponent } from "@jahia/javascript-modules-library";
import type { AccordionItemProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:accordionItem",
    displayName: "Accordion Item",
  },
  ({ title, body }: AccordionItemProps) => {
    const id = `acc-${Math.random().toString(36).slice(2, 8)}`;

    return (
      <details className="accordion-item">
        <summary className="accordion-title">
          <h3 className="field-accordiontitle">{title || ""}</h3>
          <i className="accordion-icon fa-solid fa-chevron-down" />
        </summary>
        <div className="accordion-body">
          {body && <div dangerouslySetInnerHTML={{ __html: body }} />}
        </div>
      </details>
    );
  },
);
