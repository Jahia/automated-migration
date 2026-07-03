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
        (os.path.join("Page", "basic.server.tsx"), f"{module}/src/templates/Page/basic.server.tsx"),
        ("rawRoot.ts", f"{module}/src/components/rawRoot.ts"),
        (os.path.join("RawHtml", "default.server.tsx"), f"{module}/src/components/RawHtml/default.server.tsx"),
    ]
    for rel, dst in plan:
        src = os.path.join(SRC, rel)
        content = open(src, encoding="utf-8").read().replace("$NS", a.ns)
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
        tpl = open(os.path.join(SRC, "SkeletonView.tsx.template"), encoding="utf-8").read()
        for c in (m.get("components") or []):
            if not c.get("skeleton"):
                continue
            nt = c["nodeType"]
            short = nt.split(":")[-1]
            comp_dir = f"{module}/src/components/{short[0].upper()}{short[1:]}"
            os.makedirs(comp_dir, exist_ok=True)
            out = (tpl.replace("$NODETYPE", nt)
                      .replace("$DISPLAYNAME", re.sub(r'"', "'", c.get("name") or short))
                      .replace("$RELROOT", ".."))
            with open(f"{comp_dir}/default.server.tsx", "w", encoding="utf-8") as f:
                f.write(out)
            n_views += 1

    print(f"[install_shell_templates] fidelity shell (ns={a.ns}) -> {module}/src "
          f"(Layout, basic template, RawHtml view"
          + (f", {n_views} skeleton view(s)" if n_views else "") + ")")


if __name__ == "__main__":
    main()
