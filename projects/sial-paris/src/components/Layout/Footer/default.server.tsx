import { jahiaComponent, buildNodeUrl } from "@jahia/javascript-modules-library";
import type { Props } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "sialp:footer",
    displayName: "Footer",
  },
  (props: Props) => {
    const {
      newsletterHeading,
      newsletterPlaceholder,
      gdprText,
      sialLogo,
      comexposiumLogo,
      copyrightText,
    } = props;

    return (
      <footer>
        <div id="footer" className="container">
          <div className="row">
            <div className="component footer container-fluid px-0">
              <div className="component-content">
                <div className="bg-top-footer">
                  <div className="grid-1">
                    {newsletterHeading && <h3>{newsletterHeading}</h3>}
                    <form>
                      <input
                        type="email"
                        placeholder={newsletterPlaceholder}
                        aria-label="Email"
                      />
                      <button type="submit">Envoyer</button>
                    </form>
                    {gdprText && (
                      <div dangerouslySetInnerHTML={{ __html: gdprText }} />
                    )}
                  </div>
                </div>
                <div className="bg-white">
                  <div className="grid-2">
                    {sialLogo && (
                      <img src={buildNodeUrl(sialLogo)} alt="SIAL Paris" />
                    )}
                    {comexposiumLogo && (
                      <img src={buildNodeUrl(comexposiumLogo)} alt="Comexposium" />
                    )}
                    {copyrightText && <p>{copyrightText}</p>}
                  </div>
                  <div className="ml">
                    <div className="field-lien" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </footer>
    );
  },
);
