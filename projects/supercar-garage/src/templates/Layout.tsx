import {
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
 *   1. theme-tokens.css   — :root token defaults
 *   2. base / core / main CSS files (color/font literals replaced with var(--token))
 *   3. inline <style>     — site-node :root{} overrides from usgmix:siteTheme mixin
 *   4. themeOverrideCss   — uploaded override stylesheet (wins the cascade)
 */
export const Layout = ({ title, children }: { title: string; children: ReactNode }) => {
  const { currentResource, renderContext } = useServerContext();
  const lang = currentResource.getLocale().getLanguage();

  // Read site node for theme mixin props
  const siteNode = renderContext.getSite() as unknown as JCRNodeWrapper;
  const themePrimaryColor = getProp(siteNode, "themePrimaryColor");
  const themeSecondaryColor = getProp(siteNode, "themeSecondaryColor");
  const themeAccentColor = getProp(siteNode, "themeAccentColor");
  const themeTextColor = getProp(siteNode, "themeTextColor");
  const themeBackgroundColor = getProp(siteNode, "themeBackgroundColor");
  const themeFontHeading = getProp(siteNode, "themeFontHeading");
  const themeFontBody = getProp(siteNode, "themeFontBody");
  const themeOverrideCss = getWeakRef(siteNode, "themeOverrideCss");

  // Build the inline :root{} override block — only emit tokens that are set
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
        {/* 1. Token defaults — load first so all downstream CSS can use var(--token) */}
        <AddResources type="css" resources={buildModuleFileUrl("static/css/theme-tokens.css")} />

        {/* 2. Vendor and theme stylesheets (colors/fonts rewritten to var(--token) by tokenizer) */}
        <AddResources type="css" resources={buildModuleFileUrl("static/css/core-libraries.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/bootstrap4.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/base-theme.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/main-theme.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/swiffy-slider.css")} />
        <AddResources type="css" resources={buildModuleFileUrl("static/css/inline.css")} />

        {/* Vite-compiled module styles */}
        <AddResources type="css" resources={buildModuleFileUrl("dist/assets/style.css")} />

        {/* 3. Site-node :root{} inline override — editor-managed theme tokens */}
        <style dangerouslySetInnerHTML={{ __html: inlineRootBlock }} />

        {/* FA Pro -> Free remap so icons don't render as blank boxes */}
        <style dangerouslySetInnerHTML={{ __html: `
@font-face {
  font-family: "Font Awesome 6 Pro";
  font-style: normal; font-weight: 900; font-display: block;
  src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");
}
@font-face {
  font-family: "Font Awesome 6 Pro";
  font-style: normal; font-weight: 400; font-display: block;
  src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-regular-400.woff2") format("woff2");
}
@font-face {
  font-family: "Font Awesome 6 Pro";
  font-style: normal; font-weight: 300; font-display: block;
  src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-regular-400.woff2") format("woff2");
}
@font-face {
  font-family: "Font Awesome 6 Brands";
  font-style: normal; font-weight: 400; font-display: block;
  src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-brands-400.woff2") format("woff2");
}
@font-face {
  font-family: "Font Awesome 6 Sharp";
  font-style: normal; font-weight: 900; font-display: block;
  src: url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");
}
        ` }} />

        <title>{title}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />

        {/* 4. Uploaded override stylesheet — wins the cascade (loaded last) */}
        {themeOverrideCss ? (
          <link rel="stylesheet" href={buildNodeUrl(themeOverrideCss)} />
        ) : null}
      </head>
      <body>{children}</body>
    </html>
  );
};
