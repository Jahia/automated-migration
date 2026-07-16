import {
  AbsoluteArea,
  AddResources,
  Render,
  buildModuleFileUrl,
  useServerContext,
} from "@jahia/javascript-modules-library";
import type { JCRNodeWrapper } from "org.jahia.services.content";
import { createElement, type ReactNode } from "react";

import "modern-normalize/modern-normalize.css";
import "./global.css";
import cssManifest from "./css-manifest.json";
import jsManifest from "./js-manifest.json";

type ShellLevel = { tag: string; attrs: Record<string, string>; before: string; after: string };
type HeadItem = {
  kind: "css" | "script" | "inline-script" | "style";
  href?: string;
  src?: string;
  defer?: boolean;
  async?: boolean;
  type?: string;
  attrs?: Record<string, string>;
  text?: string;
};
export type Shell = {
  bodyAttrs: Record<string, string>;
  mainAttrs: Record<string, string>;
  levels: ShellLevel[];
  innerLevels?: ShellLevel[];
  head?: HeadItem[];
  // zone-bridge shells carry NO chrome markup in levels (header/nav/footer are
  // contributed AbsoluteArea blocks) — this flag keeps the areas rendering.
  // Vision-pipeline shells embed chrome verbatim in levels and omit the flag.
  chromeAreas?: boolean;
};

// SEMANTIC (archetype) model: the chrome is contributed Jahia components —
// a tree-driven MainNavigation + header/footer in AbsoluteAreas — so those
// areas must ALWAYS render, even on pages that carry a fidelity shell (whose
// captured chrome we ignore in this model). install_shell_templates flips this
// to true for the archetype model; the fidelity model keeps it false (there the
// source chrome is embedded in the shell and shell.chromeAreas gates the areas).
const CHROME_ALWAYS = $CHROME_ALWAYS;

/** Balanced sibling markup, DOM-transparent for layout (display:contents). */
const Raw = ({ html }: { html?: string }) =>
  html ? <div style={{ display: "contents" }} dangerouslySetInnerHTML={{ __html: html }} /> : null;

/** Source attributes -> React DOM props (class -> className; style strings dropped). */
const domAttrs = (attrs: Record<string, string> | undefined) => {
  const { class: cls, style: _ignored, ...rest } = attrs ?? {};
  const out: Record<string, unknown> = { ...rest };
  if (cls) out.className = cls;
  return out;
};

/**
 * Places `children` in an html page.
 *
 * Fidelity contract (ground-truth gate): the SOURCE site's stylesheets and
 * head scripts load verbatim, in source order, from static/assets (see
 * import_assets.py). When the page carries a SHELL spec (extract_content
 * page_shell -> `shell` child node), the source body attributes, the exact
 * ancestor chain down to <main>, and the balanced markup around it (chrome,
 * sprites, drupalSettings, body scripts) are recomposed around the main Area —
 * body-class-keyed CSS and site JS behave as on the source. Without a shell,
 * chrome falls back to absolute areas (rule 16).
 */
export const Layout = ({
  title,
  children,
  shell,
}: {
  title: string;
  children: ReactNode;
  shell?: Shell | null;
}) => {
  const { currentResource, renderContext } = useServerContext();
  const lang = currentResource.getLocale().getLanguage();

  // AbsoluteArea parent MUST be the home page node — NOT renderContext.getSite()
  const siteNode = renderContext.getSite() as unknown as JCRNodeWrapper;
  const homePage = siteNode.getNode("home") as JCRNodeWrapper;

  // inner wrapper chain (e.g. Drupal's region--content) recomposed around the
  // Area — top groups load at real-section altitude with wrappers intact
  // SEMANTIC (archetype) model: IGNORE the shell's captured source-body chrome.
  // shell.levels/innerLevels carry the source header/nav/footer/cookie markup in
  // their before/after raw HTML (and shell.head carries the source SPA scripts
  // that hydrate it). In this model the chrome is OUR contributed Jahia
  // components, so render a clean <main> with no source chrome — keeping only
  // body/main attrs. The fidelity model still recomposes the full source shell.
  const inner =
    shell && !CHROME_ALWAYS
      ? (shell.innerLevels ?? []).reduceRight<ReactNode>(
          (acc, lvl) =>
            createElement(
              lvl.tag,
              domAttrs(lvl.attrs),
              <Raw key="b" html={lvl.before} />,
              acc,
              <Raw key="a" html={lvl.after} />,
            ),
          children,
        )
      : children;
  const main = shell ? (
    <main {...domAttrs(shell.mainAttrs)}>{inner}</main>
  ) : CHROME_ALWAYS ? (
    // archetype model: the source CSS keys its layout off main.<classes>
    // descendant selectors — ALWAYS restore the source main context
    // ($MAIN_CLASS is stamped at install time from the captured shell)
    <main className="$MAIN_CLASS">{inner}</main>
  ) : (
    children
  );
  const body =
    shell && !CHROME_ALWAYS
      ? shell.levels.reduceRight<ReactNode>(
          (inner, lvl, i) =>
            i === 0 ? (
              <>
                <Raw html={lvl.before} />
                {inner}
                <Raw html={lvl.after} />
              </>
            ) : (
              createElement(
                lvl.tag,
                domAttrs(lvl.attrs),
                <Raw key="b" html={lvl.before} />,
                inner,
                <Raw key="a" html={lvl.after} />,
              )
            ),
          main,
        )
      : main;

  return (
    <html lang={lang}>
      <head>
        <meta charSet="utf-8" />
        {/* consent-framework locator iframes (__tcfapiLocator/__uspapiLocator)
            are injected in-flow by the source site's consent JS; the consent
            platform's own (external, offline-blocked) CSS normally hides them.
            Without it they render as ~304x154 white boxes that shift the whole
            page (ground-truth Δh). display:none removes them from flow.
            Archetype model: no consent JS runs at all — rule not needed. */}
        {!CHROME_ALWAYS && (
          <style
            dangerouslySetInnerHTML={{
              __html:
                'iframe[name="__tcfapiLocator"],iframe[name="__uspapiLocator"]{display:none !important}',
            }}
          />
        )}
        {/* module archetype layout CSS — ALWAYS linked, and FIRST so the source
            site's captured stylesheets (rendered below in shell mode) override
            on ties. The shell-head branch emits only the SOURCE's <link>s, so
            the module's own bundled CSS is not injected there; without this
            every ArchetypeSection wrapper (hero cover, card grid, nav bar…)
            renders unstyled. Shipped as a static asset by install_shell_templates. */}
        <link rel="stylesheet" href={buildModuleFileUrl("static/semantic.css")} />
        {shell?.head
          ? // per-page source head, in source order (Drupal aggregates per page;
            // drupalSettings JSON + behaviors init live here)
            shell.head.map((h, i) => {
              // archetype model: drop the source SPA scripts — they hydrate the
              // source's own header/mega-menu/cookie-consent, which we replace
              // with contributed Jahia chrome. Keep only the stylesheets/styles
              // (they still style the inner content of each semantic component).
              if (CHROME_ALWAYS && (h.kind === "script" || h.kind === "inline-script"))
                return null;
              if (h.kind === "css" && h.href)
                return <link key={i} rel="stylesheet" href={h.href} />;
              if (h.kind === "script" && h.src)
                return (
                  <script
                    key={i}
                    src={h.src}
                    defer={h.defer || undefined}
                    async={h.async || undefined}
                  />
                );
              if (h.kind === "inline-script")
                return (
                  <script
                    key={i}
                    {...domAttrs(h.attrs)}
                    dangerouslySetInnerHTML={{ __html: h.text ?? "" }}
                  />
                );
              if (h.kind === "style")
                return <style key={i} dangerouslySetInnerHTML={{ __html: h.text ?? "" }} />;
              return null;
            })
          : cssManifest.map((css) => (
              <AddResources key={css} type="css" resources={buildModuleFileUrl(css)} />
            ))}
        {/* archetype model: NEVER load the source SPA bundles — they rebuild the
            source's own chrome (mega-menu, cookie consent, notification bar) on
            the client, exactly the junk this model replaces with Jahia chrome. */}
        {!CHROME_ALWAYS &&
          !shell?.head &&
          jsManifest.map((s) => (
            <script
              key={s.src}
              src={buildModuleFileUrl(s.src)}
              defer={s.defer || undefined}
              async={s.async || undefined}
            />
          ))}
        <title>{title}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </head>
      <body {...domAttrs(shell?.bodyAttrs)}>
        {(CHROME_ALWAYS || !shell || shell.chromeAreas) && (
          <AbsoluteArea name="header" parent={homePage} />
        )}
        {(CHROME_ALWAYS || !shell || shell.chromeAreas) && (
          <AbsoluteArea name="nav" parent={homePage} />
        )}
        {/* tree-driven breadcrumb (virtual node — parameterless, no storage) */}
        {CHROME_ALWAYS && <Render content={{ nodeType: "$NS:breadcrumb" } as never} />}
        {body}
        {(CHROME_ALWAYS || !shell || shell.chromeAreas) && (
          <AbsoluteArea name="footer" parent={homePage} />
        )}
      </body>
    </html>
  );
};
