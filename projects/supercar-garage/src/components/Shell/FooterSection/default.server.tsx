import {
  buildNodeUrl,
  getChildNodes,
  jahiaComponent,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { FooterSectionProps } from "./types.js";

function resolveLinkHref(node: JCRNodeWrapper): string {
  try {
    if (!node.hasProperty("j:linkType")) return "#";
    const type = node.getProperty("j:linkType").getString();
    if (type === "internal" && node.hasProperty("j:linknode")) {
      return buildNodeUrl(node.getProperty("j:linknode").getNode() as JCRNodeWrapper);
    }
    if (type === "external" && node.hasProperty("j:url")) {
      return node.getProperty("j:url").getString() ?? "#";
    }
  } catch (_) {}
  return "#";
}

function getStringProp(node: JCRNodeWrapper, name: string): string {
  try {
    return node.hasProperty(name) ? node.getProperty(name).getString() : "";
  } catch (_) {
    return "";
  }
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "usg:footerSection",
    displayName: "Footer Section",
  },
  (props: FooterSectionProps) => {
    const { currentNode } = useServerContext();

    const socialLinks = getChildNodes(
      currentNode,
      -1,
      0,
      (n: JCRNodeWrapper) => n.isNodeType("usg:socialLink"),
    );

    const ctaButtons = getChildNodes(
      currentNode,
      -1,
      0,
      (n: JCRNodeWrapper) => n.isNodeType("usg:ctaButton"),
    );

    return (
      <div className="component footerm2 container-fluid px-0 col-12">
        <div className="component-content">
          <div className="bg-top-footer">
            <div className="grid-1">
              {/* Social links column */}
              <div className="socials">
                {props.socialHeading && (
                  <div className="field-texte-reseaux-sociaux">{props.socialHeading}</div>
                )}
                {socialLinks.map((link: JCRNodeWrapper) => {
                  const href = resolveLinkHref(link);
                  const iconClass = getStringProp(link, "iconClass");
                  return (
                    <a
                      key={link.getPath()}
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      aria-label={getStringProp(link, "platform")}
                    >
                      <div>
                        <i className={iconClass} aria-hidden="true" />
                      </div>
                    </a>
                  );
                })}
              </div>

              {/* CTA links column */}
              <div className="link-container">
                {ctaButtons.map((btn: JCRNodeWrapper) => {
                  const href = resolveLinkHref(btn);
                  const label = getStringProp(btn, "ctaLabel");
                  if (!label) return null;
                  return (
                    <div key={btn.getPath()} className="field-lien">
                      <a href={href}>{label}</a>
                    </div>
                  );
                })}
              </div>

              {/* Newsletter form */}
              <div className="form-control-checkbox">
                {props.newsletterLabel && (
                  <div className="field-texte-newsletter">{props.newsletterLabel}</div>
                )}
                <div className="row">
                  <form method="post">
                    <input
                      type="email"
                      name="newsletter-email"
                      placeholder={props.newsletterPlaceholder ?? ""}
                      aria-label={props.newsletterLabel ?? "Email"}
                      maxLength={255}
                    />
                    <label>
                      <input type="checkbox" name="newsletter-optin" value="true" />
                      {props.newsletterConsentLabel && (
                        <span>{props.newsletterConsentLabel}</span>
                      )}
                    </label>
                    {props.newsletterSubmitLabel && (
                      <input
                        type="submit"
                        value={props.newsletterSubmitLabel}
                      />
                    )}
                  </form>
                </div>
              </div>
            </div>
          </div>

          {/* White section: main logo + partner logos + legal links */}
          <div className="bg-white">
            <div className="grid-2">
              {/* Partner logo 1 */}
              {props.partnerLogo1 && (
                <div>
                  <div className="img-logo">
                    <div>
                      <img
                        src={buildNodeUrl(props.partnerLogo1)}
                        alt={props.partnerLabel1 ?? ""}
                        loading="lazy"
                        style={{ maxHeight: "90px" }}
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Partner logo 2 */}
              {props.partnerLogo2 && (
                <div>
                  <div className="img-container">
                    {props.partnerLabel2 && (
                      <div className="field-texte-1">{props.partnerLabel2}</div>
                    )}
                    <div>
                      <img
                        src={buildNodeUrl(props.partnerLogo2)}
                        alt={props.partnerLabel2 ?? ""}
                        className="img-cover"
                        loading="lazy"
                        style={{ maxHeight: "90px" }}
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Partner logo 3 */}
              {props.partnerLogo3 && (
                <div>
                  <div className="img-container">
                    {props.partnerLabel3 && (
                      <div className="field-texte-2">{props.partnerLabel3}</div>
                    )}
                    <div>
                      <img
                        src={buildNodeUrl(props.partnerLogo3)}
                        alt={props.partnerLabel3 ?? ""}
                        className="img-cover"
                        loading="lazy"
                        style={{ maxHeight: "90px" }}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Legal links */}
          <div className="ml">
            {props.legalPlanSite && (
              <div className="field-lien">
                <span>{props.legalPlanSite}</span>
              </div>
            )}
            {props.legalMentions && (
              <div className="field-lien">
                <span>{props.legalMentions}</span>
              </div>
            )}
            {props.legalData && (
              <div className="field-lien">
                <span>{props.legalData}</span>
              </div>
            )}
            {props.legalCookies && (
              <div className="field-lien">
                <span>{props.legalCookies}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  },
);
