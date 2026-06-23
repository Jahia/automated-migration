import { jahiaComponent, getChildNodes, buildNodeUrl, Render } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { Props } from "./types.js";

function prop(node: JCRNodeWrapper, name: string): string | undefined {
  try {
    return node.hasProperty(name) ? node.getProperty(name).getString() : undefined;
  } catch {
    return undefined;
  }
}

/** Resolve a footerLink's href from the contributor-selected j:linkType. */
function linkHref(node: JCRNodeWrapper): string {
  try {
    const t = prop(node, "j:linkType");
    if (t === "internal" && node.hasProperty("j:linknode"))
      return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
    if (t === "external" && node.hasProperty("j:url")) return node.getProperty("j:url").getString();
  } catch {
    /* noop */
  }
  return "#";
}

/** Footer-specific view for the shared social-link component (different styling
 *  from the top-bar default view). */
jahiaComponent(
  { componentType: "view", nodeType: "sialp:socialLink", name: "footer", displayName: "Social Link (footer)" },
  (_props: Props, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const icon = prop(currentNode, "iconClass");
    return (
      <a
        href={linkHref(currentNode)}
        target="_blank"
        rel="noopener noreferrer nofollow"
        aria-label={prop(currentNode, "label") || "Social"}
        className="footer-social-link"
      >
        {icon && <i className={icon} aria-hidden="true"></i>}
      </a>
    );
  },
);

/** Minimal standalone view for a footer link (used in edit mode; the footer view
 *  renders them inline grouped by footerGroup). */
jahiaComponent(
  { componentType: "view", nodeType: "sialp:footerLink", displayName: "Footer Link" },
  (props: Props, { currentNode }: { currentNode: JCRNodeWrapper }) => (
    <a href={linkHref(currentNode)}>{prop(currentNode, "label")}</a>
  ),
);

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:footer",
    displayName: "Footer",
  },
  (
    {
      communityText,
      faqText,
      newsletterHeading,
      newsletterPlaceholder,
      newsletterLabel,
      gdprText,
      organisedByLabel,
      sialLogo,
      comexposiumLogo,
      stockfoodLogo,
      copyrightText,
      submitButtonLabel,
    }: Props,
    { currentNode }: { currentNode: JCRNodeWrapper },
  ) => {
    const socials = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("sialp:socialLink"),
    );
    const links = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("sialp:footerLink"),
    );
    const byGroup = (g: string) => links.filter((n) => (prop(n, "footerGroup") || "legal") === g);
    const cta = byGroup("cta");
    const legal = byGroup("legal");
    const faq = byGroup("faq")[0];

    return (
      <footer>
        <div id="footer" className="container">
          <div className="row">
            <div className="component footer container-fluid px-0">
              <div className="component-content">
                {/* ── Top band: community + social + FAQ ── */}
                <div className="bg-top-footer">
                  <div className="grid-1">
                    {communityText && <h3>{communityText}</h3>}
                    {socials.length > 0 && (
                      <div className="social-links">
                        {socials.map((s: JCRNodeWrapper) => (
                          <Render key={s.getPath()} node={s} view="footer" />
                        ))}
                      </div>
                    )}
                    {faqText && <p className="footer-faq">{faqText}</p>}
                    {faq && (
                      <a href={linkHref(faq)} className="btn btn-link footer-faq-link">
                        {prop(faq, "label")}
                      </a>
                    )}
                  </div>

                  {/* ── Newsletter + consent ── */}
                  <div className="footer-newsletter bg-white">
                    {newsletterHeading && <h4>{newsletterHeading}</h4>}
                    <form>
                      <input type="email" placeholder={newsletterPlaceholder} aria-label="Email" />
                      <button type="submit">{submitButtonLabel ?? "Envoyer"}</button>
                    </form>
                    {newsletterLabel && (
                      <label className="footer-consent">
                        <input type="checkbox" /> <span>{newsletterLabel}</span>
                      </label>
                    )}
                    {gdprText && (
                      <div className="footer-gdpr" dangerouslySetInnerHTML={{ __html: gdprText }} />
                    )}
                  </div>
                </div>

                {/* ── CTA buttons ── */}
                {cta.length > 0 && (
                  <div className="footer-cta-row">
                    {cta.map((c: JCRNodeWrapper) => (
                      <a key={c.getPath()} href={linkHref(c)} className="btn btn-solid-primary footer-cta">
                        <span>{prop(c, "label")}</span>
                      </a>
                    ))}
                  </div>
                )}

                {/* ── Organised by + logos ── */}
                <div className="footer-organised">
                  {organisedByLabel && <span className="footer-organised-label">{organisedByLabel}</span>}
                  <div className="footer-logos">
                    {comexposiumLogo && <img src={buildNodeUrl(comexposiumLogo)} alt="Comexposium" />}
                    {stockfoodLogo && <img src={buildNodeUrl(stockfoodLogo)} alt="StockFood" />}
                    {sialLogo && <img src={buildNodeUrl(sialLogo)} alt="SIAL Paris" />}
                  </div>
                </div>

                {/* ── Legal links ── */}
                {legal.length > 0 && (
                  <ul className="footer-legal">
                    {legal.map((l: JCRNodeWrapper) => (
                      <li key={l.getPath()}>
                        <a href={linkHref(l)}>{prop(l, "label")}</a>
                      </li>
                    ))}
                  </ul>
                )}

                {copyrightText && <p className="copyright">{copyrightText}</p>}
              </div>
            </div>
          </div>
        </div>
      </footer>
    );
  },
);
