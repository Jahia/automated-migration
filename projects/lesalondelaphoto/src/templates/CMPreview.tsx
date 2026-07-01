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

/**
 * CMPreview — shared wrapper for `cm` views (jContent back-office preview).
 *
 * jContent renders a content node's `cm` view in the editor preview panel. Unlike
 * the public site, that panel has no page Layout, so none of the module's CSS is
 * loaded and the component would appear unstyled. This wrapper loads the SAME
 * stylesheet cascade Layout uses (theme tokens -> vendor/theme -> compiled module
 * CSS -> corrections -> FA remap -> fonts + editor-managed :root brand overrides)
 * around the previewed node, WITHOUT the header/footer/AbsoluteArea chrome.
 *
 * Used by every `src/components/<Type>/cm.server.tsx`.
 */

const FA_REMAP =
  `@font-face{font-family:"Font Awesome 6 Pro";font-style:normal;font-weight:900;font-display:block;src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");}` +
  `@font-face{font-family:"Font Awesome 6 Pro";font-style:normal;font-weight:400;font-display:block;src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-regular-400.woff2") format("woff2");}` +
  `@font-face{font-family:"Font Awesome 6 Brands";font-style:normal;font-weight:400;font-display:block;src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-brands-400.woff2") format("woff2");}` +
  `@font-face{font-family:"Font Awesome 6 Sharp";font-style:normal;font-weight:900;font-display:block;src:url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/fa-solid-900.woff2") format("woff2");}`;

/** Safely read a string property from a JCR node, returns "" if absent. */
function getProp(node: JCRNodeWrapper | null, name: string): string {
  try {
    if (node && node.hasProperty(name)) {
      return node.getProperty(name).getString() ?? "";
    }
  } catch {
    // property not set
  }
  return "";
}

/** Safely read a weakreference property, returns the node or null. */
function getWeakRef(node: JCRNodeWrapper | null, name: string): JCRNodeWrapper | null {
  try {
    if (node && node.hasProperty(name)) {
      return node.getProperty(name).getNode() as JCRNodeWrapper;
    }
  } catch {
    // not set
  }
  return null;
}

export const CMPreview = ({ children }: { children: ReactNode }) => {
  const { renderContext } = useServerContext();

  // Editor-managed brand overrides from the site node (same tokens as Layout).
  // Guarded: preview must still render if the site node is unavailable.
  let siteNode: JCRNodeWrapper | null = null;
  try {
    siteNode = renderContext.getSite() as unknown as JCRNodeWrapper;
  } catch {
    siteNode = null;
  }

  const rootOverrides: string[] = [];
  const push = (prop: string, varName: string) => {
    const v = getProp(siteNode, prop);
    if (v) rootOverrides.push(`  ${varName}: ${v};`);
  };
  push("themePrimaryColor", "--color-primary");
  push("themeSecondaryColor", "--color-secondary");
  push("themeAccentColor", "--color-accent");
  push("themeTextColor", "--color-text");
  push("themeBackgroundColor", "--color-bg");
  push("themeFontHeading", "--font-heading");
  push("themeFontBody", "--font-body");
  const inlineRootBlock =
    rootOverrides.length > 0 ? `:root{\n${rootOverrides.join("\n")}\n}` : "";
  const themeOverrideCss = getWeakRef(siteNode, "themeOverrideCss");

  return (
    <>
      {/* 1. Token defaults first */}
      <AddResources type="css" resources={buildModuleFileUrl("static/css/theme-tokens.css")} />
      {/* 2. Vendor + theme stylesheets */}
      <AddResources type="css" resources={buildModuleFileUrl("static/css/core-libraries.css")} />
      <AddResources type="css" resources={buildModuleFileUrl("static/css/bootstrap4.css")} />
      <AddResources type="css" resources={buildModuleFileUrl("static/css/model-site.css")} />
      <AddResources type="css" resources={buildModuleFileUrl("static/css/main-theme.css")} />
      <AddResources type="css" resources={buildModuleFileUrl("static/css/swiffy-slider.css")} />
      {/* Vite-compiled module styles (global.css + CSS modules + normalize) */}
      <AddResources type="css" resources={buildModuleFileUrl("dist/assets/style.css")} />
      {/* Corrections last */}
      <AddResources type="css" resources={buildModuleFileUrl("static/css/site-corrections.css")} />

      {/* FA Pro 6 font-family remap */}
      <style dangerouslySetInnerHTML={{ __html: FA_REMAP }} />
      {/* Editor-managed :root brand overrides */}
      {inlineRootBlock && <style dangerouslySetInnerHTML={{ __html: inlineRootBlock }} />}
      {/* Text fonts */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Rubik:wght@400;500;700&display=swap"
      />
      {/* Uploaded override stylesheet — wins the cascade */}
      {themeOverrideCss ? <link rel="stylesheet" href={buildNodeUrl(themeOverrideCss)} /> : null}

      <main>{children}</main>
    </>
  );
};
