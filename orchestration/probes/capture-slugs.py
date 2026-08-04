#!/usr/bin/env python3
"""capture-slugs.py — CAPTURE IDENTITY gate (producer: nav_scope_crawl / crawl-site).

A page's slug is its identity for the whole rest of the pipeline: create_pages
names the JCR page after it, build_nav_tree moves it by it, every ledger and
pixel gate joins on it. A malformed slug space is therefore a silent, expensive
defect class, and it has exactly one recurring cause: a LOCALE-PREFIXED source
crawled without `--lang`.

On https://www.lesalondelaphoto.com/fr-FR the start page is `/fr-FR`, so without
`--lang fr-FR`:
  * the home page is slugged `fr-FR` (never `home`), so every "is home present"
    check passes on a page that is not modelled as home;
  * every inner page carries the prefix (`fr-FR_salon_qui-expose`), so the page
    tree roots in a bogus `fr-FR` node and the IA is wrong before nav even runs.

This gate FAILS on:
  1. no `home` slug in the inventory,
  2. any slug carrying a locale prefix (explicit --lang, or any BCP-47-shaped
     leading segment — a locale that was never declared is still a defect),
  3. duplicate slugs (two captures claiming one identity),
  4. an empty inventory.

Usage: capture-slugs.py <project_path> [--lang fr-FR]
"""
import argparse
import json
import os
import re
import sys

# A leading path segment that looks like a locale: fr, fr-FR, en_us, pt-BR…
LOCALEISH = re.compile(r"^[a-z]{2}([-_][A-Za-z]{2,4})?$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_path")
    ap.add_argument("--lang", default="")
    a = ap.parse_args()
    inv_path = f"{a.project_path.rstrip('/')}/workflow-output/page-inventory.json"
    try:
        inv = json.load(open(inv_path))
    except (OSError, ValueError) as e:
        sys.exit(f"FAIL capture-slugs: cannot read {inv_path} ({e})")

    pages = inv.get("pages") or []
    slugs = [p.get("slug") or "" for p in pages]
    fails = []

    if not slugs:
        fails.append("inventory holds 0 pages")
    if "home" not in slugs:
        fails.append(f"no 'home' slug ({len(slugs)} page(s) captured) — the start "
                     "URL was not recognised as the site root")

    declared = a.lang.lower()
    prefixed = []
    for s in slugs:
        head = s.split("_", 1)[0]
        if (declared and head.lower() == declared) or LOCALEISH.match(head):
            prefixed.append(s)
    if prefixed:
        hint = f"--lang {a.lang}" if a.lang else "--lang <locale>"
        fails.append(f"{len(prefixed)} slug(s) carry a locale prefix "
                     f"(e.g. {', '.join(prefixed[:3])}) — re-crawl with {hint}")

    # LEDGER MONOTONICITY (2026-08-03): the inventory only ever grows within a run —
    # capture adds pages, nothing removes them. A pass that REPLACES it instead of
    # merging silently drops earlier captures (the seed crawl truncated 159 -> 27 while
    # the captures stayed on disk). Compare against the cache: every cached page that
    # belongs to this locale must be in the ledger.
    import glob as _glob
    cache = f"{a.project_path.rstrip('/')}/.reference/cache/_crawl"
    cached = [f for f in _glob.glob(f"{cache}/**/*.html", recursive=True)]
    if cached and len(cached) > len(slugs) * 1.2:
        fails.append(f"inventory holds {len(slugs)} page(s) but {len(cached)} page(s) are "
                     f"CACHED — a pass replaced the ledger instead of merging into it, so "
                     f"earlier captures are invisible downstream")

    # ERROR PAGES ARE NOT CONTENT (2026-08-04). The crawler cached whatever the origin
    # returned, so two programme URLs that answer "500 — Internal server error" landed in
    # the corpus as pages: no headings, no fields, and they would have loaded as titleless
    # empty entity nodes. A 4xx/5xx body served with a 200 status is invisible to a
    # status-code check, so match the RENDERED page: an error title with no real content.
    import glob as _g2
    mirror_dir = f"{a.project_path.rstrip('/')}/workflow-output/local-mirror"
    ERR = re.compile(r"(?:^|\W)(4\d\d|5\d\d)\s*[—–-]\s*|internal server error|"
                     r"page not found|something went wrong|page introuvable|"
                     r"erreur interne", re.I)
    errpages = []
    for f in sorted(_g2.glob(f"{mirror_dir}/*.html")):
        try:
            html = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        title = re.sub(r"\s+", " ", (mt.group(1) if mt else "")).strip()
        if not ERR.search(title):
            continue
        # measure the MAIN region: an error page still ships the full site chrome
        # (7220 chars of header/nav/footer here), so a whole-page threshold never
        # fires. Its <main> held 204 chars and zero headings.
        # the error page has NO <main> AT ALL — falling back to the whole document
        # measured 7220 chars of chrome and the test never fired. A missing main
        # region under an error title IS the signal; every real page here has one.
        mm = re.search(r"<main[^>]*>(.*?)</main>", html, re.S | re.I)
        region = mm.group(1) if mm else ""
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", region)).strip()
        heads = len(re.findall(r"<h[12]\b", region or html, re.I))
        if (mm is None or len(text) < 600) and heads == 0:
            errpages.append((os.path.basename(f)[:-5], title[:48]))
    if errpages:
        fails.append(f"{len(errpages)} captured page(s) are SOURCE ERROR PAGES, not "
                     f"content: " + "; ".join(f"{s2} ({t})" for s2, t in errpages[:5])
                     + " — drop them from the ledger or record them as accepted "
                       "source defects; they would load as empty nodes")

    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    if dupes:
        fails.append(f"duplicate slug(s): {', '.join(dupes[:5])}")

    if fails:
        print(f"FAIL capture-slugs [{inv_path}]")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print(f"PASS capture-slugs: {len(slugs)} page(s), home present, "
          f"no locale-prefixed or duplicate slug"
          + (f" (lang {a.lang})" if a.lang else ""))


if __name__ == "__main__":
    main()
