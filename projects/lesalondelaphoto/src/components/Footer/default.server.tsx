import { buildNodeUrl, getChildNodes, jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
import { useTranslation } from "react-i18next";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { FooterProps } from "./types.js";

function resolveLinkUrl(child: JCRNodeWrapper): string | undefined {
  try {
    if (child.isNodeType("lsp:footerLink")) {
      if (child.hasProperty("j:linknode")) {
        const linked = child.getProperty("j:linknode").getNode() as JCRNodeWrapper;
        return buildNodeUrl(linked);
      }
      if (child.hasProperty("j:url")) {
        return child.getProperty("j:url").getString();
      }
    }
    if (child.isNodeType("lsp:socialLink")) {
      if (child.hasProperty("j:url")) {
        return child.getProperty("j:url").getString();
      }
    }
  } catch {
    // no link
  }
  return "#";
}

function resolveLabel(child: JCRNodeWrapper): string {
  try {
    if (child.isNodeType("lsp:footerLink") && child.hasProperty("label")) {
      return child.getProperty("label").getString();
    }
  } catch {
    // no label
  }
  return child.getName();
}

const PLATFORM_ICONS: Record<string, string> = {
  instagram: "fa-brands fa-instagram",
  facebook: "fa-brands fa-facebook-f",
  linkedin: "fa-brands fa-linkedin-in",
  x: "fa-brands fa-x-twitter",
  youtube: "fa-brands fa-youtube",
};

function socialIcon(child: JCRNodeWrapper): string | undefined {
  try {
    if (child.isNodeType("lsp:socialLink") && child.hasProperty("platform")) {
      const plat = child.getProperty("platform").getString();
      return PLATFORM_ICONS[plat];
    }
  } catch {/* */ }
  return undefined;
}

function socialUrl(child: JCRNodeWrapper): string | undefined {
  try {
    if (child.isNodeType("lsp:socialLink") && child.hasProperty("j:url")) {
      return child.getProperty("j:url").getString();
    }
  } catch {/* */ }
  return undefined;
}

function socialAriaLabel(child: JCRNodeWrapper): string {
  try {
    if (child.isNodeType("lsp:socialLink") && child.hasProperty("platform")) {
      const plat = child.getProperty("platform").getString();
      const labels: Record<string, string> = {
        instagram: "Instagram",
        facebook: "Facebook",
        linkedin: "LinkedIn",
        x: "X (Twitter)",
        youtube: "YouTube",
      };
      return labels[plat] || plat;
    }
  } catch {/* */ }
  return child.getName();
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:footer",
    displayName: "Footer",
    properties: { "jmix:hiddenType": "true" },
  },
  ({ footerText, image }: FooterProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { t } = useTranslation();
    const { renderContext } = useServerContext();
    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;

    const footerLinkNodes = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:footerLink"),
    );

    const socialLinkNodes = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:socialLink"),
    );

    return (
      <footer id="footer" className="component footer container-fluid px-0">
        <div className="component-content">
          <div className="bg-top-footer">
            <div className="grid-1">
              <div className="socials">
                <div className="field-texte-reseaux-sociaux">{t("footer.joinCommunity")}</div>
                {socialLinkNodes.map((child) => {
                  const icon = socialIcon(child);
                  const url = socialUrl(child);
                  if (!url || !icon) return null;
                  return (
                    <a key={child.getIdentifier()} target="_blank" rel="noopener noreferrer nofollow" href={url} aria-label={socialAriaLabel(child)}>
                      <div><i className={icon} /></div>
                    </a>
                  );
                })}
              </div>

              <div className="link-container">
                {footerLinkNodes.map((child) => (
                  <div key={child.getIdentifier()} className="field-lien">
                    <a href={resolveLinkUrl(child)}>
                      {resolveLabel(child)}
                    </a>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-white">
            <div className="grid-2">
              <div>
                <div className="img-logo">
                  <a title="Home" href={buildNodeUrl(homePage)}>
                    <div>
                      {image && (
                        <img
                          src={buildNodeUrl(image)}
                          alt={t("footer.siteLogoAlt")}
                          loading="lazy"
                          style={{ maxHeight: "90px" }}
                        />
                      )}
                    </div>
                  </a>
                </div>
              </div>
            </div>
          </div>

          {footerText && (
            <div className="ml">
              <div dangerouslySetInnerHTML={{ __html: footerText }} />
            </div>
          )}
        </div>
      </footer>
    );
  },
);
