import {
  getChildNodes,
  Render,
  buildNodeUrl,
  jahiaComponent,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

function imgUrl(props: Props): string | null {
  return props.image ? buildNodeUrl(props.image) : (props.imageExternalUrl || null);
}
function href(props: Props): string {
  const { "j:linkType": t, "j:linknode": n, "j:url": u } = props;
  return t === "internal" && n ? buildNodeUrl(n) : t === "external" && u ? u : "#";
}

/** Large left card (SXA `.col-l.card`) — first trend, image + text. */
jahiaComponent(
  { componentType: "view", nodeType: "sialp:trendCard", name: "large", displayName: "Trend Card (large)" },
  (props: Props) => {
    const src = imgUrl(props);
    return (
      <div className="col-l card">
        <div className="description d-flex justify-content-between">
          <div>
            {props.heading && <h3 className="field-title1">{props.heading}</h3>}
            {props.excerpt && <div className="field-description-1">{props.excerpt}</div>}
          </div>
          {props.ctaLabel && <a className="btn-outline-white" href={href(props)}><span>{props.ctaLabel}</span></a>}
        </div>
        {src && <img className="img-cover" src={src} alt={props.heading ?? ""} />}
      </div>
    );
  },
);

/** Small stacked card (SXA `.col-r .card`). */
jahiaComponent(
  { componentType: "view", nodeType: "sialp:trendCard", displayName: "Trend Card" },
  (props: Props) => {
    const src = imgUrl(props);
    return (
      <div className="card">
        <div className="description d-flex justify-content-between">
          <div>
            {props.heading && <h3 className="field-title2">{props.heading}</h3>}
            {props.excerpt && <div className="field-description-2">{props.excerpt}</div>}
          </div>
          {props.ctaLabel && <a className="btn-outline-white" href={href(props)}><span>{props.ctaLabel}</span></a>}
        </div>
        {src && <img className="img-cover" src={src} alt={props.heading ?? ""} />}
      </div>
    );
  },
);

/** TENDANCES ET INNOVATIONS section — SXA `content mosaic`: header + 1 large card + 2 stacked + CTA. */
jahiaComponent(
  { componentType: "view", nodeType: "sialp:trendsSection", displayName: "Trends Section" },
  (props: Props, { currentNode }) => {
    const { surtitle, heading, intro, ctaLabel } = props;
    const ctaHref = href(props);
    const cards = getChildNodes(currentNode as unknown as JCRNodeWrapper, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("sialp:trendCard"),
    );
    const [first, ...rest] = cards;
    return (
      <section className="component content container-fluid mosaic bg-gray-1 col-12">
        <div className="component-content">
          <div className="container-bp">
            <div className="wrapper">
              <div>
                <div className="simple-title col-12">
                  {surtitle && (
                    <div className="focus-title">
                      <div className="sub-title field-surtitre">{surtitle}</div>
                    </div>
                  )}
                </div>
                {heading && <h2 className="field-titre-global">{heading}</h2>}
                {intro && <div className="field-description-globale">{intro}</div>}
              </div>
              {first && <Render node={first} view="large" />}
              <div className="col-r">
                {rest.map((c: JCRNodeWrapper) => (
                  <Render key={c.getPath()} node={c} />
                ))}
              </div>
            </div>
            {ctaLabel && (
              <div className="text-center">
                <a className="btn btn-primary mt-50" href={ctaHref}><span>{ctaLabel}</span></a>
              </div>
            )}
          </div>
        </div>
      </section>
    );
  },
);
