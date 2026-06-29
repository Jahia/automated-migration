import { buildNodeUrl, getChildNodes, jahiaComponent, useServerContext } from "@jahia/javascript-modules-library";
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
  } catch {
    // no link
  }
  return "#";
}

function resolveLabel(child: JCRNodeWrapper): string {
  try {
    if (child.hasProperty("label")) {
      return child.getProperty("label").getString();
    }
  } catch {
    // no label
  }
  return child.getName();
}

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:footer",
    displayName: "Footer",
    properties: { "jmix:hiddenType": "true" },
  },
  ({ footerText }: FooterProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { renderContext } = useServerContext();
    const site = renderContext.getSite() as unknown as JCRNodeWrapper;
    const homePage = site.getNode("home") as JCRNodeWrapper;

    const children = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:footerLink"),
    );

    return (
      <div className="component footer container-fluid px-0">
        <div className="component-content">
          <div className="bg-top-footer">
            <div className="grid-1">
              <div className="socials">
                <div className="field-texte-reseaux-sociaux">Rejoignez la communauté</div>
                <a target="_blank" rel="noopener noreferrer nofollow" href="https://instagram.com/salonphotovideoparis" aria-label="Instagram">
                  <div><i className="fa-brands fa-instagram" /></div>
                </a>
                <a target="_blank" rel="noopener noreferrer nofollow" href="https://www.facebook.com/salonphotoetvideo/" aria-label="Facebook">
                  <div><i className="fa-brands fa-facebook-f" /></div>
                </a>
                <a target="_blank" rel="noopener noreferrer nofollow" href="https://www.linkedin.com/company/salon-photo-et-video/" aria-label="LinkedIn">
                  <div><i className="fa-brands fa-linkedin-in" /></div>
                </a>
                <a target="_blank" rel="noopener noreferrer nofollow" href="https://twitter.com/SalonPhotoParis" aria-label="X (Twitter)">
                  <div><i className="fa-brands fa-x-twitter" /></div>
                </a>
                <a target="_blank" rel="noopener noreferrer nofollow" href="https://www.youtube.com/channel/UCzlJeVhJhZpgz0xJqriBx7w" aria-label="YouTube">
                  <div><i className="fa-brands fa-youtube" /></div>
                </a>
              </div>

              <div className="link-container">
                {children.map((child) => (
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
                      <img
                        src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 50'%3E%3Crect fill='%23111827' width='200' height='50'/%3E%3Ctext fill='white' font-family='Arial' font-size='14' x='10' y='32'%3ELe Salon de la Photo%3C/text%3E%3C/svg%3E"
                        alt="Le Salon de la Photo"
                        loading="lazy"
                        style={{ maxHeight: "90px" }}
                      />
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
      </div>
    );
  },
);
