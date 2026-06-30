import {
  AbsoluteArea,
  AddResources,
  buildModuleFileUrl,
  buildNodeUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import type { ReactNode } from "react";

import "modern-normalize/modern-normalize.css";
import "./global.css";

/** Safely read a string property from a JCR node, returns "" if absent. */
function getProp(node: JCRNodeWrapper, name: string): string {
  try {
    if (node.hasProperty(name)) {
      return node.getProperty(name).getString() ?? "";
    }
  } catch {
    // property not set
  }
  return "";
}

/** Safely read a weakreference property, returns the node or null. */
function getWeakRef(node: JCRNodeWrapper, name: string): JCRNodeWrapper | null {
  try {
    if (node.hasProperty(name)) {
      return node.getProperty(name).getNode() as JCRNodeWrapper;
    }
  } catch {
    // not set
  }
  return null;
}

/** Places `children` in an html page and wires the theme cascade:
 *   1. theme-tokens.css — :root token defaults (must load first)
 *   2. vendor + theme stylesheets (color/font literals rewritten to var(--token))
 *   3. inline <style> — site-node :root{} overrides from lspmix:siteTheme mixin
 *   4. themeOverrideCss — uploaded override stylesheet (wins the cascade)
 */
export const Layout = ({ title, children }: { title: string; children: ReactNode }) => {
  const { currentResource, renderContext } = useServerContext();
  const lang = currentResource.getLocale().getLanguage();

  const siteNode = renderContext.getSite() as unknown as JCRNodeWrapper;
  // AbsoluteArea parent MUST be the home page node — NOT renderContext.getSite()
  const homePage = siteNode.getNode("home") as JCRNodeWrapper;

  const description = getProp(currentResource as unknown as JCRNodeWrapper, "jcr:description");

  const themePrimaryColor = getProp(siteNode, "themePrimaryColor");
  const themeSecondaryColor = getProp(siteNode, "themeSecondaryColor");
  const themeAccentColor = getProp(siteNode, "themeAccentColor");
  const themeTextColor = getProp(siteNode, "themeTextColor");
  const themeBackgroundColor = getProp(siteNode, "themeBackgroundColor");
  const themeFontHeading = getProp(siteNode, "themeFontHeading");
  const themeFontBody = getProp(siteNode, "themeFontBody");
  const themeOverrideCss = getWeakRef(siteNode, "themeOverrideCss");

  const rootOverrides: string[] = [];
  if (themePrimaryColor) rootOverrides.push(`  --color-primary: ${themePrimaryColor};`);
  if (themeSecondaryColor) rootOverrides.push(`  --color-secondary: ${themeSecondaryColor};`);
  if (themeAccentColor) rootOverrides.push(`  --color-accent: ${themeAccentColor};`);
  if (themeTextColor) rootOverrides.push(`  --color-text: ${themeTextColor};`);
  if (themeBackgroundColor) rootOverrides.push(`  --color-bg: ${themeBackgroundColor};`);
  if (themeFontHeading) rootOverrides.push(`  --font-heading: ${themeFontHeading};`);
  if (themeFontBody) rootOverrides.push(`  --font-body: ${themeFontBody};`);

  const inlineRootBlock =
    rootOverrides.length > 0
      ? `:root{\n${rootOverrides.join("\n")}\n}\nbody { height: auto !important; overflow-x: hidden; }`
      : `body { height: auto !important; overflow-x: hidden; }`;

  return (
    <html lang={lang}>
      <head>
        {/* 1. Token defaults — first so all downstream CSS can use var(--token) */}
        <AddResources type="css" resources={buildModuleFileUrl("static/css/theme-tokens.css")} />

        {/* 2. Vendor + theme stylesheets (literals rewritten to var(--token)) */}
        <AddResources type="css" resources={buildModuleFileUrl("static/css/core-libraries.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/bootstrap4.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/model-site.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/main-theme.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/swiffy-slider.css")} />

        {/* Vite-compiled module styles */}
        <AddResources type="css" resources={buildModuleFileUrl("dist/assets/style.css")} />

        {/* FA Pro 6 font-family remap — point Pro names at FA Free CDN files */}
        <style
          dangerouslySetInnerHTML={{
            __html: `@font-face{font-family:"Font Awesome 6 Pro";font-style:normal;font-weight:900;font-display:block;src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");}@font-face{font-family:"Font Awesome 6 Pro";font-style:normal;font-weight:400;font-display:block;src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-regular-400.woff2") format("woff2");}@font-face{font-family:"Font Awesome 6 Brands";font-style:normal;font-weight:400;font-display:block;src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-brands-400.woff2") format("woff2");}@font-face{font-family:"Font Awesome 6 Sharp";font-style:normal;font-weight:900;font-display:block;src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");}`,
          }}
        />

        {/* 3. Site-node :root{} inline override — editor-managed theme tokens */}
        <style dangerouslySetInnerHTML={{ __html: inlineRootBlock }} />

        {/* Text fonts: the reference uses Roboto (body) + Rubik (headings). The theme
            CSS names them but never loaded them, so it fell back to serif. Load them. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Rubik:wght@400;500;700&display=swap"
        />

        <title>{title}</title>
        {description && <meta name="description" content={description} />}
        {!description && <meta name="description" content={title} />}
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />

        {/* 4. Uploaded override stylesheet — wins the cascade (loaded last) */}
        {themeOverrideCss ? <link rel="stylesheet" href={buildNodeUrl(themeOverrideCss)} /> : null}
      </head>
      <body>
        <AbsoluteArea name="topBar" nodeType="lsp:topBar" parent={homePage} />
        <AbsoluteArea name="nav" nodeType="lsp:mainNav" parent={homePage}/>
        <main id="main-content">
          <h1 style={{ position: "absolute", width: "1px", height: "1px", padding: "0", margin: "-1px", overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap", border: "0" }}>{title}</h1>
          {children}
        </main>
        <AbsoluteArea name="footer" nodeType="lsp:footer" parent={homePage} />

        {/* swiffy-slider auto-init (carousels load via AddResources, init can miss late-injected DOM) */}
        <AddResources type="javascript" resources={buildModuleFileUrl("static/js/swiffy-slider.js")} />
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){function init(){if(window.swiffyslider){window.swiffyslider.init();}else{setTimeout(init,200);}}if(document.readyState!=="loading"){init();}else{document.addEventListener("DOMContentLoaded",init);}})();`,
          }}
        />
      </body>
    </html>
  );
};
