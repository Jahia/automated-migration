import { buildNodeUrl, getChildNodes, jahiaComponent, Render } from "@jahia/javascript-modules-library";
import { useTranslation } from "react-i18next";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { PromoBlockProps } from "./types.js";

function resolveCta(node: PromoBlockProps, current: JCRNodeWrapper): { url?: string; label?: string } {
  const linkType = node["j:linkType"];
  if (!linkType || linkType === "none") return {};
  const label = node.ctaLabel || undefined;
  if (linkType === "internal") {
    try {
      if (current.hasProperty("j:linknode")) {
        const linked = current.getProperty("j:linknode").getNode() as JCRNodeWrapper;
        return { url: buildNodeUrl(linked), label };
      }
    } catch {
      // no internal link
    }
  } else if (linkType === "external") {
    try {
      if (current.hasProperty("j:url")) {
        return { url: current.getProperty("j:url").getString(), label };
      }
    } catch {
      // no external url
    }
  }
  return {};
}

function resolveVideoUrl(node: PromoBlockProps, current: JCRNodeWrapper): string | undefined {
  try {
    if (current.hasProperty("j:url")) {
      const url = current.getProperty("j:url").getString();
      const match = url.match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([\w-]{11})/);
      if (match) {
        return `https://www.youtube-nocookie.com/embed/${match[1]}?autoplay=0&rel=0`;
      }
      return url;
    }
  } catch {
    // no video url
  }
  return undefined;
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:promoBlock",
    displayName: "Promo Block",
  },
  (node: PromoBlockProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { t } = useTranslation();
    const heading = node.heading;
    const description = node.description;
    const cta = resolveCta(node, currentNode);
    const videoUrl = resolveVideoUrl(node, currentNode);
    const ctaChildren = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:ctaButton"),
    );

    return (
      <div className="component video-content-block container bg-gray-1 col-12">
        <div className="component-content">
          <div className="container-bp">
            <div className="row">
              <div className="col-md-6">
                <div className="simple-title">
                  <div>
                    <div className="back-title arriere-titre">{t("promoBlock.videoEyebrow")}</div>
                  </div>
                </div>
                <div className="row">
                  {videoUrl && (
                    <iframe
                      width="560"
                      height="315"
                      src={videoUrl}
                      title={heading || "Video"}
                      frameBorder="0"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                      referrerPolicy="strict-origin-when-cross-origin"
                      allowFullScreen
                      style={{ maxWidth: "100%" }}
                    />
                  )}
                </div>
              </div>
              <div className="col-md-6 align-self-center py-md-70 py-sm-30">
                <div className="row justify-content-center">
                  <div className="offset-lg-2 col-lg-9">
                    <i className="fa-brands fa-youtube fa-3x" />
                  </div>
                  <div className="offset-lg-2 col-lg-9">
                    {heading && <h2 className="field-title">{heading}</h2>}
                    {description && (
                      <div
                        className="rich-text field-description"
                        dangerouslySetInnerHTML={{ __html: description }}
                      />
                    )}
                    {ctaChildren.map((child) => (
                      <Render key={child.getIdentifier()} node={child as JCRNodeWrapper} view="default" />
                    ))}
                    {cta.url && cta.label && (
                      <a href={cta.url} className="btn btn-primary mt-30" rel="nofollow">
                        <span>{cta.label}</span>
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  },
);
