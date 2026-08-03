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
