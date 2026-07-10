import { getChildNodes, jahiaComponent, Render, useServerContext } from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { TopBarProps } from "./types.js";

jahiaComponent(
  {
    componentType: "view",
    nodeType: "lsp:topBar",
    displayName: "Top Bar",
    properties: { "jmix:hiddenType": "true" },
  },
  ({ hashtag }: TopBarProps, { currentNode }: { currentNode: JCRNodeWrapper }) => {
    const { renderContext } = useServerContext();
    const isEdit = renderContext.isEditMode();

    const socialLinks = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:socialLink"),
    );
    const ctaButtons = getChildNodes(currentNode, -1, 0, (n: JCRNodeWrapper) =>
      n.isNodeType("lsp:ctaButton"),
    );

    if (isEdit) {
      return (
        <div className="component top-bar col-12">
          <div className="component-content">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "8px" }}>
              {[...socialLinks, ...ctaButtons].map((child) => (
                <div key={child.getIdentifier()} style={{ border: "1px solid #ccc", padding: "8px" }}>
                  <Render node={child as JCRNodeWrapper} view="default" readOnly />
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    // Faithful transcription of the reference `.component.top-bar.top-navbar.container-fluid`
    // block — every class kept so the imported theme CSS applies (support-create-view Step 1).
    const propOf = (n: JCRNodeWrapper, name: string): string => {
      try { return n.hasProperty(name) ? n.getProperty(name).getString() : ""; } catch { return ""; }
    };
    return (
      <div className="component top-bar top-navbar container-fluid">
        <div className="component-content">
          <div className="row align-items-center parent-row">
            <div className="col-auto d-md-down-none socials">
              {socialLinks.map((s) => {
                const url = propOf(s, "j:url") || propOf(s, "url");
                const platform = propOf(s, "platform").toLowerCase();
                const icon = platform.includes("insta") ? "fa-instagram"
                  : platform.includes("face") ? "fa-facebook-f"
                  : platform.includes("link") ? "fa-linkedin-in"
                  : (platform.includes("twitt") || platform === "x") ? "fa-x-twitter"
                  : platform.includes("you") ? "fa-youtube" : "fa-link";
                return (
                  <a key={s.getIdentifier()} target="_blank" rel="noopener noreferrer nofollow" href={url || "#"}>
                    <div><i className={`fa-brands ${icon}`} /></div>
                  </a>
                );
              })}
              {hashtag && <div className="text-white fs-sm field-texte">{hashtag}</div>}
            </div>
            <div className="col-auto ">
              {ctaButtons.map((c) => {
                const url = propOf(c, "j:url") || propOf(c, "url");
                const label = propOf(c, "label") || propOf(c, "jcr:title");
                const icon = propOf(c, "iconClass") || "fa-regular fa-store";
                return (
                  <a key={c.getIdentifier()} title="" href={url || "#"} target="">
                    <div className="call-back">
                      <i className={icon} />
                      <div className="field-texte-1">{label}</div>
                    </div>
                  </a>
                );
              })}
            </div>
            <div className="col-auto d-flex">
              <a title="" href="/recherche" target="">
                <div className="search"><i className="fa-solid fa-magnifying-glass" /></div>
              </a>
            </div>
          </div>
        </div>
      </div>
    );
  },
);
