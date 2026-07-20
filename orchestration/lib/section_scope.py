#!/usr/bin/env python3
"""section_scope.py — the SOURCE's multi-section IA, from its own nav data.

Operator correction (2026-07-20): singpost has THREE sections — Personal /
Small Business / Enterprise — each with its OWN tree; the migration had
modeled ONE section's menu around a hand-picked page sample. The full wrapper
(PERSONAL/BUSINESS/ENTERPRISE with complete subtrees) ships on EVERY page in
the Navbar island's `navMobile` prop; this tool makes it the scope authority:

  section-navs.json   all sections' trees (labels + hrefs, nested)
  --urls SECTION      the section's internal URLs, one per line (crawl scope
                      for crawl-site --url-list; nav-driven, bounded)
  --sitemap SECTION   IA lines for orchestration/sitemaps/<p>.txt (crawl-slug
                      segments, the build_nav_tree/parenting convention)

Usage:
  section_scope.py <project> [--page home] [--urls SECTION] [--sitemap SECTION]
"""
import argparse
import html as htmllib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_nav import _dec  # noqa: E402


def section_trees(page_html):
    """{SECTION_LABEL: [items...]} from the Navbar island's navMobile prop.
    Both attribute quote styles (Astro single-quotes JSON-bearing attrs)."""
    for pat in (r"<astro-island[^>]*\sprops='([^']*)'",
                r"<astro-island[^>]*\sprops=\"([^\"]*)\""):
        for m in re.finditer(pat, page_html):
            raw = htmllib.unescape(m.group(1))
            if '"navMobile"' not in raw:
                continue
            try:
                props = json.loads(raw)
            except ValueError:
                continue
            nav = _dec(props.get("navMobile", [1, []]))
            if nav and all(isinstance(x, dict) and x.get("subMenu") for x in nav):
                return {x.get("label") or f"S{i}": x["subMenu"]
                        for i, x in enumerate(nav)}
    return {}


def internal_urls(items, out=None):
    out = out if out is not None else []
    for it in items or []:
        h = (it.get("href") or "").split("#")[0].split("?")[0]
        if h.startswith("/") and h != "/" and h not in out:
            out.append(h)
        internal_urls(it.get("subMenu"), out)
    return out


def slug(href):
    return href.strip("/").replace("/", "_")


def _slugify(label):
    s = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return s or "group"


def sitemap_lines(items, trail=None, labels=None):
    """IA lines: each LINKED nav node contributes trail+its-crawl-slug; an
    hrefless GROUP header becomes a SYNTHETIC section segment (slugified
    label — the existing receiving/receiving convention: build_nav_tree
    creates it as a jnt:page menu node). `labels` collects {segment: label}
    for the sitemap .labels.json so synthetic pages get real titles."""
    trail = trail or []
    lines = []
    for it in items or []:
        h = (it.get("href") or "").split("#")[0].split("?")[0]
        if h.startswith("/") and h != "/":
            path = trail + [slug(h)]
            lines.append("/".join(path))
            # the MENU label, not the page's SEO <title> ("Delivery Solutions
            # – First & Last Mile Services | SingPost" is not a menu entry)
            if labels is not None and (it.get("label") or "").strip():
                labels[slug(h)] = it["label"].strip()
            lines += sitemap_lines(it.get("subMenu"), path, labels)
        elif it.get("subMenu"):
            seg = _slugify(it.get("label"))
            if labels is not None:
                labels[seg] = it.get("label") or seg
            path = trail + [seg]
            lines.append("/".join(path))
            lines += sitemap_lines(it.get("subMenu"), path, labels)
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--page", default="home")
    ap.add_argument("--urls", help="print SECTION's internal URLs")
    ap.add_argument("--sitemap", help="print SECTION's sitemap IA lines")
    a = ap.parse_args()
    mp = f"projects/{a.project}/workflow-output/local-mirror/{a.page}.html"
    trees = section_trees(open(mp, encoding="utf-8", errors="replace").read())
    if not trees:
        sys.exit("FAIL: no navMobile section wrapper found — single-tree site?")
    out = f"projects/{a.project}/workflow-output/section-navs.json"
    json.dump(trees, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"[section_scope] {len(trees)} section(s) -> {out}: "
          f"{ {k: len(internal_urls(v)) for k, v in trees.items()} }",
          file=sys.stderr)
    if a.urls:
        for u in internal_urls(trees[a.urls]):
            print(u)
    if a.sitemap:
        labels = {}
        for l in sitemap_lines(trees[a.sitemap], labels=labels):
            print(l)
        if labels:
            lp = f"orchestration/sitemaps/{a.project}.labels.json"
            try:
                cur = json.load(open(lp))
            except (FileNotFoundError, ValueError):
                cur = {}
            for seg, lab in labels.items():
                cur.setdefault(seg, lab)  # FLAT {slug: label} — build_nav_tree's convention
            json.dump(cur, open(lp, "w"), indent=1, ensure_ascii=False)
            print(f"[section_scope] {len(labels)} synthetic label(s) -> {lp}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
