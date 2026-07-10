import { buildModuleFileUrl, buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type React from "react";
import type { Props } from "./types.js";

const FALLBACK_IMAGES = [
  "static/assets/images/slide-1.jpg",
  "static/assets/images/slide-2.jpg",
];

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:ctaDualCards",
    displayName: "CTA Dual Cards",
  },
  (props: Props) => {
    const {
      leftHeading,
      leftImage,
      leftCtaLabel,
      leftLinkNode,
      rightHeading,
      rightImage,
      rightCtaLabel,
      rightLinkNode,
    } = props;

    const leftImageUrl = leftImage
      ? buildNodeUrl(leftImage)
      : buildModuleFileUrl(FALLBACK_IMAGES[0]);
    const rightImageUrl = rightImage
      ? buildNodeUrl(rightImage)
      : buildModuleFileUrl(FALLBACK_IMAGES[1]);
    const leftHref = leftLinkNode ? buildNodeUrl(leftLinkNode) : "#";
    const rightHref = rightLinkNode ? buildNodeUrl(rightLinkNode) : "#";

    return (
      <section className="component picture-grid container-bp col-12">
        <div className="component-content">
          <div className="card">
            <div className="card-img">
              <img className="img-cover" src={leftImageUrl} alt="" />
            </div>
            <div className="card-body" style={{ position: "relative", zIndex: 1 } as React.CSSProperties}>
              {leftHeading && (
                <h2 className="text-truncate-3 field-picturegriditemtitre">
                  {leftHeading}
                </h2>
              )}
              {leftCtaLabel && (
                <a className="btn btn-solid-white field-picturegriditemcta" href={leftHref}>
                  <span>{leftCtaLabel}</span>
                </a>
              )}
            </div>
          </div>
          <div className="card">
            <div className="card-img">
              <img className="img-cover" src={rightImageUrl} alt="" />
            </div>
            <div className="card-body" style={{ position: "relative", zIndex: 1 } as React.CSSProperties}>
              {rightHeading && (
                <h2 className="text-truncate-3 field-picturegriditemtitre">
                  {rightHeading}
                </h2>
              )}
              {rightCtaLabel && (
                <a className="btn btn-solid-white field-picturegriditemcta" href={rightHref}>
                  <span>{rightCtaLabel}</span>
                </a>
              )}
            </div>
          </div>
        </div>
      </section>
    );
  },
);
