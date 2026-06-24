import { buildNodeUrl, jahiaComponent } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

const bgMap: Record<string, string> = {
  yellow: "#FCE003",
  dark: "#1a1a2e",
  white: "#ffffff",
};

const textMap: Record<string, string> = {
  yellow: "#000000",
  dark: "#ffffff",
  white: "#000000",
};

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:ctaBanner",
    displayName: "CTA Banner",
  },
  (props: Props) => {
    const { heading, subtext, ctaLabel, backgroundColor, backgroundImage, parallax } = props;
    const linkType = props["j:linkType"];
    const linknode = props["j:linknode"];
    const url = props["j:url"];

    const href =
      linkType === "internal" && linknode
        ? buildNodeUrl(linknode)
        : linkType === "external" && url
          ? url
          : undefined;

    // ── Parallax / image-background variant ──────────────────────────────
    const bgImageUrl = backgroundImage ? buildNodeUrl(backgroundImage) : undefined;
    if (bgImageUrl) {
      const hasOverlay = Boolean(heading || subtext || (href && ctaLabel));
      const cls = `component cta-banner image-banner${parallax !== false ? " parallax-banner" : ""}${hasOverlay ? " has-overlay" : ""} col-12`;
      return (
        <section className={cls} style={{ backgroundImage: `url(${bgImageUrl})` }}>
          <div className="cta-banner-overlay">
            <div className="component-content container-bp" style={{ textAlign: "center" }}>
              {heading && <h2>{heading}</h2>}
              {subtext && <p>{subtext}</p>}
              {href && ctaLabel && (
                <a href={href} className="btn btn-solid-primary">
                  <span>{ctaLabel}</span>
                </a>
              )}
            </div>
          </div>
        </section>
      );
    }

    // ── Solid-colour variant (default) ───────────────────────────────────
    const bg = bgMap[backgroundColor ?? "yellow"] ?? bgMap.yellow;
    const color = textMap[backgroundColor ?? "yellow"] ?? textMap.yellow;
    return (
      <section className="component cta-banner col-12" style={{ background: bg, color, padding: "60px 0" }}>
        <div className="component-content container-bp" style={{ textAlign: "center" }}>
          {heading && <h2 style={{ color, marginBottom: "16px" }}>{heading}</h2>}
          {subtext && <p style={{ color, marginBottom: "32px", opacity: 0.85 }}>{subtext}</p>}
          {href && ctaLabel && (
            <a href={href} className="btn btn-solid-primary">
              <span>{ctaLabel}</span>
            </a>
          )}
        </div>
      </section>
    );
  },
);
