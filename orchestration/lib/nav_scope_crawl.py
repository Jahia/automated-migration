#!/usr/bin/env python3
"""nav_scope_crawl.py — MENU-SCOPED capture (MIGRATION-V3 Phase 0).

The IA truth is the source's NAVIGATION, never a BFS sample (the
18-random-pages failure, twice observed: hand-picked scope in the first
singpost run, then the plan's --max-pages default resurfacing it on the
rebuild). This step:

  1. crawls ONLY the start page (the seed capture);
  2. extracts the real menu from it (extract_nav — adapter-aware: hydration
     props, nav DOM) and, when the nav declares audience SECTIONS
     (section_scope), every section tree;
  3. derives the full internal URL list from the menu (+ persists the
     sitemap + labels via the section_scope/extract_nav conventions);
  4. crawls exactly that list (--url-list --merge-inventory).

Fallback honesty: when no menu is extractable, it FAILS loudly with the
evidence (a menu-less site needs an adapter, not a silent BFS sample).

Locale-prefixed sources (`/fr-FR/...`, `/en-us/...`) MUST pass `--lang`: it is
forwarded to crawl-site.py, which strips the prefix from every slug and filters
foreign-locale URLs. Without it the start page is slugged `fr-FR` instead of
`home` and every page carries the prefix — create_pages then builds a page tree
rooted in a bogus `fr-FR` node (gated by probes/capture-slugs.py).

Usage: nav_scope_crawl.py <project_path> <url> [--lang fr-FR] [--rate-delay 2]
                          [--max-asset-size 1]
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))


def sh(args):
    print("  $", " ".join(args), file=sys.stderr)
    r = subprocess.run(args)
    if r.returncode != 0:
        sys.exit(f"FAIL: {' '.join(args[:3])} -> {r.returncode}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_path")
    ap.add_argument("url")
    ap.add_argument("--rate-delay", default="2")
    ap.add_argument("--max-asset-size", default="1")
    ap.add_argument("--lang", default="",
                    help="source locale path prefix (e.g. fr-FR) — stripped from "
                         "slugs and used to filter foreign-locale URLs")
    a = ap.parse_args()
    pp = a.project_path.rstrip("/")
    project = pp.split("/")[-1]
    wo = f"{pp}/workflow-output"
    lang = ["--lang", a.lang] if a.lang else []

    # 1. seed: the start page only (gives the menu DOM).
    # --merge-inventory even here (2026-08-03): without it the seed pass REPLACES
    # page-inventory.json with its single page, so re-running this step silently
    # discards every entity detail page a previous step_entity_crawl had merged in —
    # the inventory fell 159 -> 27 while 161 captures sat in the cache, and the entity
    # crawl then re-declared 134 already-captured details as missing. The inventory is
    # a LEDGER; a seed pass must add to it, never truncate it.
    sh([sys.executable, os.path.join(HERE, "crawl-site.py"), pp, a.url,
        "--max-pages", "1", "--depth", "0", "--merge-inventory",
        *lang, "--rate-delay", a.rate_delay,
        "--max-asset-size", a.max_asset_size])
    sh([sys.executable, os.path.join(HERE, "localize_site.py"), pp,
        "--max-asset-size", "15"])

    # 2+3. menu -> URL list. Section-aware first (multi-audience navs),
    # plain nav extraction as the general path.
    urls = []
    try:
        import section_scope as SS
        home = f"{wo}/local-mirror/home.html"
        trees = SS.section_trees(open(home, encoding="utf-8",
                                      errors="replace").read())
        if trees:
            json.dump(trees, open(f"{wo}/section-navs.json", "w"), indent=1,
                      ensure_ascii=False)
            for items in trees.values():
                urls += SS.internal_urls(items)
            print(f"  ~ section nav: {len(trees)} section(s), "
                  f"{len(urls)} URL(s)", file=sys.stderr)
    except Exception as e:
        print(f"  ~ section scope n/a: {str(e)[:80]}", file=sys.stderr)
    if not urls:
        try:
            r = subprocess.run([sys.executable,
                                os.path.join(HERE, "extract_nav.py"),
                                project, "--urls"],
                               capture_output=True, text=True)
            urls = [u for u in r.stdout.split() if u.startswith("/")]
            print(f"  ~ nav extraction: {len(urls)} URL(s)", file=sys.stderr)
        except Exception:
            pass
    urls = sorted({u.split("#")[0].split("?")[0].rstrip("/")
                   for u in urls if u.startswith("/") and u != "/"
                   and not re.search(r"\.(pdf|jpe?g|png|zip|docx?)$", u, re.I)})
    if len(urls) < 3:
        sys.exit("FAIL: nav_scope_crawl — no extractable menu (found "
                 f"{len(urls)} internal URL(s)). A menu-less source needs an "
                 "adapter; refusing a silent BFS sample.")
    lst = f"{wo}/nav-urls.txt"
    open(lst, "w").write("\n".join(urls) + "\n")
    print(f"  ~ menu-scoped URL list: {len(urls)} -> {lst}", file=sys.stderr)

    # 4. the real crawl: exactly the menu's pages
    sh([sys.executable, os.path.join(HERE, "crawl-site.py"), pp, a.url,
        "--url-list", lst, "--merge-inventory",
        *lang, "--rate-delay", a.rate_delay,
        "--max-asset-size", a.max_asset_size])
    print("nav_scope_crawl: done")


if __name__ == "__main__":
    main()
