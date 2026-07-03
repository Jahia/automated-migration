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

Usage: install_shell_templates.py <project> --ns NS [--module-dir DIR]
"""
import argparse
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "fidelity-shell")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", required=True)
    ap.add_argument("--module-dir")
    a = ap.parse_args()
    module = a.module_dir or f"projects/{a.project}"
    if not os.path.isdir(f"{module}/src"):
        sys.exit(f"FAIL: {module}/src missing (scaffold first)")

    plan = [
        ("Layout.tsx", f"{module}/src/templates/Layout.tsx"),
        (os.path.join("Page", "basic.server.tsx"), f"{module}/src/templates/Page/basic.server.tsx"),
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
    print(f"[install_shell_templates] fidelity shell (ns={a.ns}) -> {module}/src "
          f"(Layout, basic template, RawHtml view)")


if __name__ == "__main__":
    main()
