import { jahiaComponent, buildNodeUrl } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

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
      rightHeading,
      rightImage,
      rightCtaLabel,
    } = props;

    const leftImageUrl = leftImage ? buildNodeUrl(leftImage) : undefined;
    const rightImageUrl = rightImage ? buildNodeUrl(rightImage) : undefined;

    return (
      <section className="component picture-grid container-bp col-12">
        <div className="component-content">
          <div className="row">
            <div className="col-md-6">
              <div className="card-img">
                {leftImageUrl && (
                  <img className="img-cover" src={leftImageUrl} alt="" />
                )}
                <div className="card">
                  <div className="card-body">
                    {leftHeading && (
                      <h2 className="text-truncate-3 field-picturegriditemtitre">
                        {leftHeading}
                      </h2>
                    )}
                    {leftCtaLabel && (
                      <a className="btn btn-solid-white field-picturegriditemcta" href="#">
                        <span>{leftCtaLabel}</span>
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
            <div className="col-md-6">
              <div className="card-img">
                {rightImageUrl && (
                  <img className="img-cover" src={rightImageUrl} alt="" />
                )}
                <div className="card">
                  <div className="card-body">
                    {rightHeading && (
                      <h2 className="text-truncate-3 field-picturegriditemtitre">
                        {rightHeading}
                      </h2>
                    )}
                    {rightCtaLabel && (
                      <a className="btn btn-solid-white field-picturegriditemcta" href="#">
                        <span>{rightCtaLabel}</span>
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  },
);
