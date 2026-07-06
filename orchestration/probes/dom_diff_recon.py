#!/usr/bin/env python3
"""dom_diff_recon — S3 proxy for the 0-DOM-change gate.

Rebuilds each page from the content-load the SAME way Layout.tsx does (shell fold:
body → levels → main → innerLevels → content Areas; + chrome AbsoluteAreas), then
runs dom_diff vs the frozen mirror. Pre-deploy, so approximate — the authoritative
gate is dom_diff render-mode (deployed EDIT vs mirror). Its job here: reveal the
drift sources to close for verbatim-first, fast.

Usage: dom_diff_recon.py <project> [--pages a,b] [--verbose]
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(__file__))
import dom_diff as D
from bs4 import BeautifulSoup

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _attrs(d):
    return "".join(f' {k}="{v if not isinstance(v, list) else " ".join(v)}"' for k, v in (d or {}).items())


def recompose_instance(insts, i, kids):
    x = insts[i]
    sk = x.get("skeleton") or ""
    so = x.get("skeletonOrig")
    f = x.get("fields") or {}
    if x.get("passthrough") or x.get("contentFree") or x.get("nonRendered"):
        return f.get("html", "") or so or sk
    lay = x.get("layout")
    if lay is not None:  # layoutSection: structured skin wraps parent-linked children.
        ch = [recompose_instance(insts, ci, kids) for ci in kids.get(i, [])]
        if lay.get("cellOpen") is not None:   # 1c columns: each child in an identical cell
            body = "".join(lay["cellOpen"] + c + lay["cellClose"] for c in ch)
        else:                                 # 1b single Area: children contiguous
            body = "".join(ch)
        return lay.get("open", "") + body + lay.get("close", "")
    if so is not None:
        # typed node: an UNEDITED node renders byte-exact to its source (rule 22),
        # and skeletonOrig IS that source. Its item children live in the instance's
        # `children` FIELD (spliced into {{child:N}} at render) — but skeletonOrig
        # already contains them inline verbatim, so this is the faithful unedited
        # render. (Earlier the proxy took the {{child:}} branch and, finding no
        # PARENT-LINKED kids, dropped typed-container content — false drift.)
        return so
    if "{{child:" in sk:  # zone / wrapper container (no skeletonOrig): parent-linked kids
        out = sk
        for n, ci in enumerate(kids.get(i, [])):
            out = out.replace("{{child:%d}}" % n, recompose_instance(insts, ci, kids))
        return out
    out = sk
    for k, v in f.items():
        if isinstance(v, str):
            out = out.replace("{{f:%s}}" % k, v)
    return out


def zone_key(z):
    if not z:
        return (1, 0)          # main / unzoned last
    if z.startswith("z") and z[1:].isdigit():
        return (0, int(z[1:]))
    return (0, 999)


def reconstruct(page_data, chrome_by_area):
    """Mirror Layout.tsx: body[chrome header/nav] + levels(main + innerLevels +
    content Areas) + [chrome footer]."""
    insts = page_data["instances"]
    shell = page_data.get("shell") or {}
    kids = {}
    for j, x in enumerate(insts):
        p = x.get("parent")
        if p is not None:
            kids.setdefault(p, []).append(j)
    # content = zones in order (z1..zK, then main), each = its top-level instances
    tops = [(j, x) for j, x in enumerate(insts)
            if x.get("parent") is None and not x.get("area")]
    tops.sort(key=lambda t: zone_key(t[1].get("zone")))
    content = "".join(recompose_instance(insts, j, kids) for j, _ in tops)

    inner = content
    for lvl in reversed(shell.get("innerLevels") or []):
        inner = (f"<{lvl['tag']}{_attrs(lvl.get('attrs'))}>{lvl.get('before','')}"
                 f"{inner}{lvl.get('after','')}</{lvl['tag']}>")
    main = f"<main{_attrs(shell.get('mainAttrs'))}>{inner}</main>" if shell else content

    body_inner = main
    levels = shell.get("levels") or []
    for idx in range(len(levels) - 1, -1, -1):
        lvl = levels[idx]
        if idx == 0:  # body level: no tag wrapper, just before/after
            body_inner = f"{lvl.get('before','')}{body_inner}{lvl.get('after','')}"
        else:
            body_inner = (f"<{lvl['tag']}{_attrs(lvl.get('attrs'))}>{lvl.get('before','')}"
                          f"{body_inner}{lvl.get('after','')}</{lvl['tag']}>")

    chrome_on = shell.get("chromeAreas", False) if shell else False
    header = (chrome_by_area.get("header", "") + chrome_by_area.get("nav", "")) if chrome_on else ""
    footer = chrome_by_area.get("footer", "") if chrome_on else ""
    return f"<body{_attrs(shell.get('bodyAttrs'))}>{header}{body_inner}{footer}</body>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--pages")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    cl = json.load(open(f"{REPO}/orchestration/content/{a.project}.content-load.json"))
    pages = cl["pages"]
    mirror = f"{REPO}/projects/{a.project}/workflow-output/local-mirror"
    # chrome instances (area-tagged) live on page 1 — group them by area
    chrome_by_area = {}
    for pg in pages.values():
        for x in pg["instances"]:
            ar = x.get("area")
            if ar:
                kids = {}
                for j, y in enumerate(pg["instances"]):
                    if y.get("parent") is not None:
                        kids.setdefault(y["parent"], []).append(j)
                idx = pg["instances"].index(x)
                chrome_by_area.setdefault(ar, "")
                chrome_by_area[ar] += recompose_instance(pg["instances"], idx, kids)
        if chrome_by_area:
            break
    slugs = a.pages.split(",") if a.pages else list(pages)
    total = 0
    for slug in slugs:
        if slug not in pages:
            continue
        recon = reconstruct(pages[slug], chrome_by_area)
        mp = f"{mirror}/{slug}.html"
        if not os.path.exists(mp):
            continue
        src = str(BeautifulSoup(open(mp, encoding="utf-8", errors="replace").read(), "lxml").body)
        _, n = D.report(src, recon, label=slug, threshold=0, show=5 if a.verbose else 0)
        total += n
    print(f"\n  TOTAL differing content nodes across {len(slugs)} page(s): {total}  (target 0)")


if __name__ == "__main__":
    main()
