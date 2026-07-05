import {
  AbsoluteArea,
  AddResources,
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
};

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
  const inner = shell
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
  ) : (
    children
  );
  const body = shell
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
        {shell?.head
          ? // per-page source head, in source order (Drupal aggregates per page;
            // drupalSettings JSON + behaviors init live here)
            shell.head.map((h, i) => {
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
        {!shell?.head &&
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
        {!shell && <AbsoluteArea name="header" parent={homePage} />}
        {!shell && <AbsoluteArea name="nav" parent={homePage} />}
        {body}
        {!shell && <AbsoluteArea name="footer" parent={homePage} />}
      </body>
    </html>
  );
};
