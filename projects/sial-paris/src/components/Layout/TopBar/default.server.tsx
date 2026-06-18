import {
  buildNodeUrl,
  jahiaComponent,
  RenderChildren,
} from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:socialLink",
    displayName: "Social Link",
  },
  (props: Props) => {
    const href =
      props["j:linkType"] === "internal" && props["j:linknode"]
        ? buildNodeUrl(props["j:linknode"] as Parameters<typeof buildNodeUrl>[0])
        : props["j:linkType"] === "external" && props["j:url"]
          ? props["j:url"]
          : "#";

    return (
      <a href={href} target="_blank" rel="noopener noreferrer nofollow" aria-label={props.label ?? ""}>
        <div>
          {props.iconClass && <i className={props.iconClass}></i>}
        </div>
      </a>
    );
  },
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:topBar",
    displayName: "Top Bar",
  },
  (props: Props) => {
    return (
      <div className="component top-bar top-navbar container-fluid">
        <div className="component-content">
          <div className="row align-items-center parent-row">
            <div className="d-md-down-none socials">
              <RenderChildren />
            </div>
            {props.communityText && (
              <div className="community-text">{props.communityText}</div>
            )}
            <div className="top-ctas">
              {props.exposantCtaLabel && props.exposantCtaUrl && (
                <a href={props.exposantCtaUrl} className="btn-exposer">
                  <span>{props.exposantCtaLabel}</span>
                </a>
              )}
              {props.espaceCtaLabel && props.espaceCtaUrl && (
                <a href={props.espaceCtaUrl} className="btn-espace">
                  <span>{props.espaceCtaLabel}</span>
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  },
);
