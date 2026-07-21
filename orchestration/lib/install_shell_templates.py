#!/usr/bin/env python3
"""install_shell_templates.py — install the AGNOSTIC fidelity-shell template set.

The fidelity-first profile (QUALITY-PLAN P1) renders every migrated page from
three generic pieces (orchestration/templates/fidelity-shell/):

  Layout.tsx              — per-page source <head> + shell composition (body
                            attrs, ancestor chain, chrome around the main Area);
                            css/js-manifest fallback when a page has no shell
  Page/basic.server.tsx   — jnt:page template reading the page's `shell` node
  RawHtml view            — verbatim passthrough view for $NS:rawHtml

Nothing here is site-specific: the only substitution is the CND namespace.
Overwrites the scaffold's vanilla Layout/basic (that is the point — the
scaffold gives structure, this gives fidelity).

With --manifest, ALSO generates one skeleton view per manifest component
flagged `skeleton: true` (P2 promotion): the view renders the node's own
captured markup with {{f:name}} markers substituted by property values —
pixel-exact when unedited, field edits reflow.

Usage: install_shell_templates.py <project> --ns NS [--module-dir DIR]
       [--manifest workflow-output/component-manifest.json]
"""
import argparse
import json
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "fidelity-shell")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", required=True)
    ap.add_argument("--module-dir")
    ap.add_argument("--manifest")
    a = ap.parse_args()
    module = a.module_dir or f"projects/{a.project}"
    if not os.path.isdir(f"{module}/src"):
        sys.exit(f"FAIL: {module}/src missing (scaffold first)")

    plan = [
        ("Layout.tsx", f"{module}/src/templates/Layout.tsx"),
        # semantic.css is a STATIC asset (served at /modules/<m>/static/semantic.css)
        # and explicitly linked by Layout — NOT a bundled import, because the
        # shell-head render path emits only the source's captured <link>s and
        # would otherwise drop the module's own layout CSS.
        ("semantic.css", f"{module}/static/semantic.css"),
        (os.path.join("Page", "basic.server.tsx"), f"{module}/src/templates/Page/basic.server.tsx"),
        ("rawRoot.ts", f"{module}/src/components/rawRoot.ts"),
        ("skeletonRender.ts", f"{module}/src/components/skeletonRender.ts"),
        (os.path.join("RawHtml", "default.server.tsx"), f"{module}/src/components/RawHtml/default.server.tsx"),
        (os.path.join("MainNavigation", "default.server.tsx"), f"{module}/src/components/MainNavigation/default.server.tsx"),
        (os.path.join("SubNavigation", "default.server.tsx"), f"{module}/src/components/SubNavigation/default.server.tsx"),
        (os.path.join("Breadcrumb", "default.server.tsx"), f"{module}/src/components/Breadcrumb/default.server.tsx"),
    ]
    # Detect the model early: the archetype (semantic) model renders its chrome
    # from contributed Jahia components (tree-driven nav + header/footer in
    # AbsoluteAreas), so the Layout must ALWAYS render those areas — flip
    # $CHROME_ALWAYS on. The fidelity model embeds source chrome in the shell,
    # so it stays gated by shell.chromeAreas (false).
    is_archetype = False
    if a.manifest and os.path.isfile(a.manifest):
        try:
            is_archetype = json.load(open(a.manifest)).get("model") == "archetype"
        except (ValueError, OSError):
            is_archetype = False
    chrome_always = "true" if is_archetype else "false"
    main_class = ""
    ma = f"projects/{a.project}/workflow-output/main-attrs.json"
    if os.path.isfile(ma):
        try:
            main_class = (json.load(open(ma)).get("mainAttrs") or {}).get("class", "") or ""
        except (ValueError, OSError):
            main_class = ""

    for rel, dst in plan:
        src = os.path.join(SRC, rel)
        content = (open(src, encoding="utf-8").read()
                   .replace("$NS", a.ns)
                   .replace("$CHROME_ALWAYS", chrome_always)
                   .replace("$MAIN_CLASS", main_class))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(content)
    # manifests must exist for the Layout imports even before import_assets runs
    for mf in ("css-manifest.json", "js-manifest.json"):
        p = f"{module}/src/templates/{mf}"
        if not os.path.isfile(p):
            with open(p, "w") as f:
                f.write("[]\n")
    n_views = 0
    if a.manifest:
        m = json.load(open(a.manifest))

        # SEMANTIC archetype model (redesign §10): emit one semantic view per
        # archetype (renders jcr:title / richtext / DAM image / CTA / children)
        # instead of skeleton {{f:}} views. The tree-driven MainNavigation view +
        # RawHtml passthrough already ship above; skip them here.
        if m.get("model") == "archetype":
            sem = open(os.path.join(SRC, "SemanticView.tsx.template"), encoding="utf-8").read()
            # HYBRID (Option B): the DEFAULT view is fidelity-first (captured
            # skeleton markup, semantic fallback); variant views stay pure
            # semantic layouts the editor can switch to.
            hyb = open(os.path.join(SRC, "HybridView.tsx.template"), encoding="utf-8").read()

            # Ship the shared, hand-authored semantic layout library as siblings
            # of the component dirs (imported '../ArchetypeSection.js' etc). These
            # are plain .tsx/.ts helpers (no jahiaComponent) + one client island;
            # the generated per-view files below stay thin and delegate MARKUP
            # here, so a proper per-archetype render + multiple views + carousel
            # interaction all come from one maintained place.
            sem_src = os.path.join(SRC, "semantic")
            for src_name, dst_name in (
                ("ArchetypeSection.tsx.template", "ArchetypeSection.tsx"),
                ("resolveSemantic.ts.template", "resolveSemantic.ts"),
                ("CarouselControls.client.tsx.template", "CarouselControls.client.tsx"),
            ):
                content = open(os.path.join(sem_src, src_name), encoding="utf-8").read().replace("$NS", a.ns)
                with open(f"{module}/src/components/{dst_name}", "w", encoding="utf-8") as f:
                    f.write(content)

            # clean stale per-component view dirs (e.g. a prior skeleton run's 40
            # one-off types) so the module is PURELY the semantic archetype set.
            # Keep the shell-shipped views + shared helpers.
            keep = {"RawHtml", "MainNavigation", "SubNavigation", "Breadcrumb", "CardItem",
                    "Cta", "Article", "JcrQuery", "GridRow"}
            for c in (m.get("components", []) or []) + (m.get("crossCutting", []) or []):
                for ntx in [c["nodeType"]] + ([c["childType"]["nodeType"]]
                                              if isinstance(c.get("childType"), dict)
                                              and c["childType"].get("nodeType") else []):
                    s = ntx.split(":")[-1]
                    keep.add(f"{s[0].upper()}{s[1:]}")
            comp_root = f"{module}/src/components"
            for entry in os.listdir(comp_root):
                p = os.path.join(comp_root, entry)
                if os.path.isdir(p) and entry not in keep:
                    import shutil
                    shutil.rmtree(p)

            def chrome_kind(nt):
                return {"siteHeader": "siteHeader", "footer": "footer"}.get(nt.split(":")[-1], "section")

            def view_names(c, needs_mr=False):
                vs = [v.get("name") for v in (c.get("views") or []) if v.get("name")] or ["default"]
                if needs_mr and "fullPage" not in vs:
                    vs.append("fullPage")
                return vs

            def write_semantic(nt, display, kind, view_name):
                nonlocal n_views
                short = nt.split(":")[-1]
                comp_dir = f"{module}/src/components/{short[0].upper()}{short[1:]}"
                os.makedirs(comp_dir, exist_ok=True)
                # RESEMBLANCE synthesis (2026-07-16): the DEFAULT view renders
                # the node's OWN source structure (HybridView: original wrappers
                # + classes -> section bands/pills/spacing) with {{f:*}} markers
                # resolved from PROPERTIES and {{child:N}} spliced through
                # RenderChild — possible now that reconcile-check guarantees the
                # fields are complete. Semantic layouts stay as variant views.
                # per-archetype default: source-structure render for sections
                # (bands/pills/spacing), SEMANTIC grid for card/carousel
                # containers — their source markup is a JS-driven slider that
                # stacks slides full-width without the source JS (observed:
                # ~7000px of stacked slides). The grid IS the no-JS rendering.
                # SKELETON-FIRST (operator review 2026-07-17): the cardGrid
                # exemption existed because JS-slider markup stacked without
                # JS — obsolete since slide decomposition splices {{child:N}}
                # items into the intact track. Semantic layouts remain as
                # VARIANT views and the fallback for uncaptured nodes.
                tpl = hyb if view_name == "default" else sem
                out = (tpl.replace("$NODETYPE", nt)
                          .replace("$DISPLAYNAME", re.sub(r'"', "'", display or short))
                          .replace("$KIND", kind)
                          .replace("$VIEWNAME", view_name))
                fn = "default.server.tsx" if view_name == "default" else f"{view_name}.server.tsx"
                with open(f"{comp_dir}/{fn}", "w", encoding="utf-8") as f:
                    f.write(out)
                n_views += 1

            ns_prefix = (m.get("passthroughType") or f"{a.ns}:x").split(":")[0]
            for c in (m.get("components", []) or []) + (m.get("crossCutting", []) or []):
                nt = c["nodeType"]
                if nt.endswith((":mainNavigation", ":subNavigation", ":rawHtml")):
                    continue  # tree-driven navs + passthrough views ship in the shell
                kind = c.get("archetype") or chrome_kind(nt)
                for vw in view_names(c, c.get("needsMainResource")):
                    if kind == "jcrQuery" and vw == "default":
                        # STRUCTURED CONTENT (2026-07-21): the listing's default
                        # view runs the REAL JCR query (mainResource cards with
                        # buildNodeUrl links) — never the generic hybrid render
                        qt = open(os.path.join(SRC, "ContentQueryList.server.tsx.template"),
                                  encoding="utf-8").read()
                        short = nt.split(":")[-1]
                        qdir = f"{module}/src/components/{short[0].upper()}{short[1:]}"
                        os.makedirs(qdir, exist_ok=True)
                        with open(f"{qdir}/default.server.tsx", "w", encoding="utf-8") as fq:
                            fq.write(qt.replace("$NODETYPE", nt)
                                       .replace("$DISPLAYNAME", re.sub(r'"', "'", c.get("name") or short)))
                        n_views += 1
                        continue
                    write_semantic(nt, c.get("name"), kind, vw)
            # mainResource CONTENT TEMPLATES (structured content 2026-07-21):
            # every entity type renders full page at its own URL — chrome via
            # Layout around the fullPage view (listing cards link here)
            mrt = open(os.path.join(SRC, "MainResourceTemplate.server.tsx.template"),
                       encoding="utf-8").read()
            for c in (m.get("components", []) or []):
                if not c.get("needsMainResource"):
                    continue
                short = c["nodeType"].split(":")[-1]
                tdir = f"{module}/src/templates/{short[0].upper()}{short[1:]}"
                os.makedirs(tdir, exist_ok=True)
                with open(f"{tdir}/default.server.tsx", "w", encoding="utf-8") as ft:
                    ft.write(mrt.replace("$NODETYPE", c["nodeType"])
                                .replace("$DISPLAYNAME", re.sub(r'"', "'", c.get("name") or short)))
                n_views += 1
            # CONTRACT reusable child objects — ONE definition each, views here
            write_semantic(f"{ns_prefix}:cardItem", "Card item", "teaserCard", "default")
            write_semantic(f"{ns_prefix}:cardItem", "Card item", "teaserCard", "compact")
            write_semantic(f"{ns_prefix}:cta", "Call to action", "ctaLink", "default")
            # entity dimension: article fullPage + card views ship even when the
            # crawl surfaced no entities (rule 22 structural set)
            if not any(x.get("needsMainResource") for x in (m.get("components") or [])):
                for vw in ("default", "card", "cm", "fullPage"):
                    write_semantic(f"{ns_prefix}:article", "Article", "article", vw)
            print(f"[install_shell_templates] fidelity shell (ns={a.ns}) -> {module}/src "
                  f"(Layout, basic template, RawHtml + tree nav, semantic layout lib; "
                  f"{n_views} SEMANTIC view(s))")
            return

        tpl = open(os.path.join(SRC, "SkeletonView.tsx.template"), encoding="utf-8").read()

        def write_view(nt, display):
            nonlocal n_views
            short = nt.split(":")[-1]
            comp_dir = f"{module}/src/components/{short[0].upper()}{short[1:]}"
            os.makedirs(comp_dir, exist_ok=True)
            out = (tpl.replace("$NODETYPE", nt)
                      .replace("$DISPLAYNAME", re.sub(r'"', "'", display or short))
                      .replace("$RELROOT", ".."))
            with open(f"{comp_dir}/default.server.tsx", "w", encoding="utf-8") as f:
                f.write(out)
            n_views += 1

        for c in (m.get("components") or []):
            if not c.get("skeleton"):
                continue
            write_view(c["nodeType"], c.get("name"))
            # child ITEM views (P2.5): items are skeleton nodes too — the view
            # is what Content Editor preview and standalone renders use
            child = c.get("childType")
            if c.get("isContainer") and isinstance(child, dict) and child.get("nodeType"):
                write_view(child["nodeType"], child.get("name"))

    # view UI strings (rule 7: never hardcoded; rule 18: en/fr keys in sync).
    # The shipped templates call t("breadcrumb.home") — the locale files MUST
    # exist or visitors see the raw key (the manual fix died with a project
    # wipe once, 2026-07-16: emission belongs to the pipeline, not to hands).
    loc_dir = f"{module}/settings/locales"
    os.makedirs(loc_dir, exist_ok=True)
    for lang, home in (("en", "Home"), ("fr", "Accueil")):
        lp = os.path.join(loc_dir, f"{lang}.json")
        try:
            cur = json.load(open(lp, encoding="utf-8"))
        except (OSError, ValueError):
            cur = {}
        cur.setdefault("breadcrumb", {}).setdefault("home", home)
        json.dump(cur, open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"[install_shell_templates] fidelity shell (ns={a.ns}) -> {module}/src "
          f"(Layout, basic template, RawHtml view"
          + (f", {n_views} skeleton view(s)" if n_views else "")
          + ", locales en+fr)")


if __name__ == "__main__":
    main()
