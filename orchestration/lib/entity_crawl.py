#!/usr/bin/env python3
"""entity_crawl.py — capture the ENTITY DETAIL pages the menu never links.

`nav_scope_crawl` captures the menu: that is the IA, and it is deliberately not the
whole site. jmix:mainResource entities live at their own URLs reached from listing
cards, so after the model declares them (`<p>.mainresource.json` urlPrefixes) their
detail pages still have to be captured — `load_main_resources` reads each entity's
core straight from the localized mirror DOM and fails honestly without it
("config declares folders but no inventory slug classifies").

URLs come from BOTH sources, unioned, because neither is complete:
  * `sitemap-urls.json` families classified as entities — the source's own published
    inventory (57 articles where the listing linked 9),
  * internal links in the scoped mirror matching an entity urlPrefix — the
    search-indexed items a sitemap omits (37 programme events, 33 catalogue details
    on Salon de la Photo).

Then: crawl exactly those URLs (--url-list --merge-inventory), localize, re-apply
scope rules. Entity slugs are excluded from page creation by create_pages, so the
page tree stays the IA.

Usage: entity_crawl.py <project> [--lang fr-FR] [--rate-delay 2] [--limit N] [--dry]
"""
import argparse
import json
import os
import re
import subprocess
import sys

from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))


def sh(args):
    print("  $", " ".join(args[:4]), "…", file=sys.stderr)
    r = subprocess.run(args)
    if r.returncode != 0:
        sys.exit(f"FAIL entity_crawl: {os.path.basename(args[1])} -> {r.returncode}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--lang", default="")
    ap.add_argument("--rate-delay", default="2")
    ap.add_argument("--limit", type=int, default=0, help="cap the crawl (0 = all)")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    p = a.project
    pp = f"projects/{p}"
    wo = f"{pp}/workflow-output"
    mrp = f"orchestration/content/{p}.mainresource.json"
    if not os.path.exists(mrp):
        print(f"entity_crawl: no {mrp} — no entities declared, nothing to crawl")
        return
    cfg = json.load(open(mrp))
    prefixes = {}
    for key, f in (cfg.get("folders") or {}).items():
        for pre in f.get("urlPrefixes") or []:
            prefixes[pre.strip("/")] = key
    if not prefixes:
        print("entity_crawl: entity map declares no urlPrefixes — nothing to crawl")
        return

    inv = json.load(open(f"{wo}/page-inventory.json"))
    captured = {pg.get("slug") for pg in inv.get("pages", [])}
    site = (inv.get("siteUrl") or "")
    host = re.sub(r"^https?://", "", site).split("/")[0]
    lang_seg = f"/{a.lang}" if a.lang else ""

    found = {}                      # rel path -> folder key

    # (1) the source's own published inventory
    smj = f"{wo}/sitemap-urls.json"
    if os.path.exists(smj):
        sm = json.load(open(smj))
        for fam, info in (sm.get("families") or {}).items():
            key = prefixes.get(fam)
            if not key:
                continue
            for rel in info.get("urls") or []:
                found[rel] = key

    # (2) card-reached details the sitemap omits (search-indexed items)
    mirror = f"{wo}/local-mirror"
    if os.path.isdir(mirror):
        for fn in sorted(f for f in os.listdir(mirror) if f.endswith(".html")):
            soup = BeautifulSoup(open(os.path.join(mirror, fn), encoding="utf-8",
                                      errors="replace").read(), "lxml")
            for anchor in (soup.body or soup).select("a[href]"):
                href = anchor["href"].strip()
                if href.startswith(("#", "mailto", "tel", "javascript")):
                    continue
                h = re.sub(r"^https?://" + re.escape(host), "", href)
                if re.match(r"^https?:/", h):
                    continue
                segs = [s for s in h.split("?")[0].split("#")[0].split("/") if s]
                if a.lang and segs and segs[0].lower() == a.lang.lower():
                    segs = segs[1:]
                rel = "/".join(segs)
                key = next((prefixes[k] for k in prefixes
                            if rel.startswith(k + "/")), None)
                if key:
                    found[rel] = key

    fresh = {r: k for r, k in found.items() if r.replace("/", "_") not in captured}
    per = {}
    for k in found.values():
        per[k] = per.get(k, 0) + 1
    print(f"entity_crawl: {len(found)} entity detail URL(s) declared "
          f"({len(fresh)} not yet captured) across {len(per)} folder(s)")
    for k, n in sorted(per.items(), key=lambda kv: -kv[1]):
        have = sum(1 for r, kk in found.items()
                   if kk == k and r.replace("/", "_") in captured)
        print(f"  {n:>5}  {k:<24} captured {have}")
    if not fresh:
        print("entity_crawl: every declared entity detail is already captured")
        return

    urls = sorted(f"{lang_seg}/{r}" for r in fresh)
    if a.limit:
        urls = urls[:a.limit]
        print(f"  ~ LIMITED to {len(urls)} URL(s) (--limit) — the rest stay uncaptured, "
              f"and entity-coverage --expect will hold the load short", file=sys.stderr)
    lst = f"{wo}/entity-urls.txt"
    open(lst, "w").write("\n".join(urls) + "\n")
    print(f"  ~ {len(urls)} URL(s) -> {lst}")
    if a.dry:
        for u in urls[:12]:
            print("   ", u)
        return

    lang = ["--lang", a.lang] if a.lang else []
    sh([sys.executable, os.path.join(HERE, "crawl-site.py"), pp, site,
        "--url-list", lst, "--merge-inventory", *lang,
        "--rate-delay", a.rate_delay, "--max-asset-size", "1"])
    sh([sys.executable, os.path.join(HERE, "localize_site.py"), pp,
        "--max-asset-size", "15"])
    sh([sys.executable, os.path.join(HERE, "scope_apply.py"), pp])
    print("entity_crawl: done — entity details captured, localized and scoped")


if __name__ == "__main__":
    main()
