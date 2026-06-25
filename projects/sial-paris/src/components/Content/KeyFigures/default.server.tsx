import {
  RenderChildren,
  buildNodeUrl,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { LucideIcon } from "../../shared/LucideIcon.js";
import type { Props } from "./types.js";

jahiaComponent(
  { componentType: "view", nodeType: "sialp:keyFigure", displayName: "Key Figure" },
  (props: Props) => {
    const { icon, number, unit, label } = props;
    const target = number ? parseInt(number.replace(/\D/g, ""), 10) : 0;
    return (
      <div className="col">
        <div>
          {icon && <div><LucideIcon name={icon} size={40} /></div>}
          <div className="figure-number">
            <span className="field-chiffre-N" data-count-target={target}>
              {number}{unit ? ` ${unit}` : ""}
            </span>
          </div>
          {label && <div className="field-description-N">{label}</div>}
        </div>
      </div>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:keyFigures",
    displayName: "Key Figures",
  },
  (props: Props, { currentNode }) => {
    const { overline, heading, ctaLabel } = props;
    const ctaHref =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"])
        : props["j:linkType"] === "external" && props["j:url"]
          ? props["j:url"]
          : undefined;
    return (
      <section className="component key-figures container bg-gray-1 animated-key-figures col-12">
        <div className="component-content">
          {(overline || heading) && (
            <div className="simple-title col-12">
              {overline && <div className="focus-title">{overline}</div>}
              {heading && <h2 className="field-titre">{heading}</h2>}
            </div>
          )}
          <div className="container-bp">
            <div className="row wrapper">
              <RenderChildren />
            </div>
            {ctaLabel && ctaHref && (
              <div className="text-center mt-4">
                <a href={ctaHref} className="btn btn-solid-primary">
                  <span>{ctaLabel}</span>
                </a>
              </div>
            )}
          </div>
        </div>
      </section>
    );
  },
);
