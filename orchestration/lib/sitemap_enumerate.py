#!/usr/bin/env python3
"""sitemap_enumerate.py — the source's OWN URL inventory, for entity completeness.

The MENU gives the IA (nav_scope_crawl); it does not give completeness. Entity
listings paginate behind a search API the migration deliberately drops, so the
captured DOM shows a page-one sample and nothing says how much is missing.
Measured on salonphoto (2026-08-03): the actus listing rendered 6 cards and linked
9 details, while `/sitemap.xml` enumerated **57** articles — a migration driven off
the capture alone would have shipped 9 of 57 news items and passed every gate. The
same sitemap also revealed a whole entity family (7 press releases) that no captured
page's main region links to at all.

So: enumerate the sitemap deterministically, classify every URL against the model,
and emit the EXPECTED per-folder entity counts that the load must later hit.

Discovery order: robots.txt `Sitemap:` directives → /sitemap.xml → /sitemap_index.xml.
`<sitemapindex>` is followed one level (child sitemaps fetched). No JS, no WAF risk
beyond a handful of GETs, rate-limited.

Writes projects/<p>/workflow-output/sitemap-urls.json:
  {source, total, localeUrls, families: {prefix: {count, urls, status}},
   expectedEntityCounts: {folder: n}, unaccounted: {prefix: count}}

Usage: sitemap_enumerate.py <project> [--lang fr-FR] [--rate-delay 1]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def discover(origin, delay):
    """(candidate sitemap urls) from robots.txt then the conventional paths."""
    cands = []
    try:
        robots = get(origin + "/robots.txt")
        cands += re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots)
    except Exception as e:                                        # noqa: BLE001
        print(f"  ~ robots.txt unavailable: {str(e)[:60]}", file=sys.stderr)
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"):
        if not any(c.endswith(path) for c in cands):
            cands.append(origin + path)
    time.sleep(delay)
    return cands


def fetch_urls(cands, delay):
    """(source_url, [loc...]) — follows one level of <sitemapindex>."""
    for cand in cands:
        try:
            xml = get(cand)
        except Exception:                                          # noqa: BLE001
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        if not locs:
            continue
        if "<sitemapindex" in xml.lower():
            out = []
            for child in locs[:25]:
                time.sleep(delay)
                try:
                    out += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", get(child))
                except Exception:                                  # noqa: BLE001
                    continue
            if out:
                return cand, out
            continue
        return cand, locs
    return None, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--lang", default="")
    ap.add_argument("--rate-delay", type=float, default=1.0)
    a = ap.parse_args()
    p = a.project
    pp = f"projects/{p}"
    inv = json.load(open(f"{pp}/workflow-output/page-inventory.json"))
    site = (inv.get("siteUrl") or "").rstrip("/")
    origin = re.match(r"^https?://[^/]+", site)
    if not origin:
        sys.exit(f"FAIL sitemap_enumerate: no usable siteUrl in the inventory ({site!r})")
    origin = origin.group(0)
    captured = {pg.get("slug") for pg in inv.get("pages", [])}

    prefixes, folder_of = {}, {}
    mrp = f"orchestration/content/{p}.mainresource.json"
    if os.path.exists(mrp):
        for key, f in (json.load(open(mrp)).get("folders") or {}).items():
            for pre in f.get("urlPrefixes") or []:
                prefixes[pre.strip("/")] = key
                folder_of[key] = f.get("type", "?")
    declared, accepted = {}, {}
    try:
        sr = json.load(open(f"{pp}/workflow-output/scope-rules.json"))
        declared = {t["path"].strip("/"): t.get("reason", "")
                    for t in (sr.get("pagesToCrawl") or [])}
        accepted = {t["path"].strip("/"): t.get("reason", "")
                    for t in (sr.get("acceptedTargets") or [])}
    except (OSError, ValueError, KeyError):
        pass

    src, locs = fetch_urls(discover(origin, a.rate_delay), a.rate_delay)
    if not locs:
        sys.exit("FAIL sitemap_enumerate: no sitemap found (robots.txt declared none "
                 "and /sitemap.xml* did not parse). A source without a sitemap must "
                 "rely on the link census alone — say so in the model's scope report.")

    def rel(u):
        u = re.sub(r"^https?://[^/]+", "", u).split("#")[0].split("?")[0]
        segs = [s for s in u.split("/") if s]
        if a.lang and segs and segs[0].lower() == a.lang.lower():
            segs = segs[1:]
        return "/".join(segs)

    locale_urls = [u for u in locs
                   if (not a.lang) or f"/{a.lang.lower()}" in u.lower()]
    fams = defaultdict(list)
    for u in locale_urls:
        r = rel(u)
        if not r:
            fams["(home)"].append("home")     # the site root IS the 'home' slug
            continue
        pre = next((k for k in prefixes if r.startswith(k + "/")), None)
        if pre:
            fams[pre].append(r)
            continue
        segs = r.split("/")
        fams["/".join(segs[:-1]) if len(segs) > 1 else r].append(r)

    def covers(url, decls):
        """a declaration covers a URL if it IS the url, a prefix of it, or lives
        under it (declaring salon/rse/souffleurs-de-sens accounts for the
        salon/rse family's single child — the granularities must meet both ways)."""
        return any(url == k or url.startswith(k + "/") or k.startswith(url + "/")
                   for k in decls)

    def status(fam, urls):
        if fam in prefixes:
            return f"entity -> {prefixes[fam]} ({folder_of.get(prefixes[fam], '?')})"
        # per-URL accounting: a family is accounted only when EVERY url in it is
        state = []
        for u in urls:
            if u.replace("/", "_") in captured:
                state.append("captured")
            elif covers(u, declared):
                state.append("declared")
            elif covers(u, accepted):
                state.append("accepted")
            else:
                state.append("unaccounted")
        miss = state.count("unaccounted")
        if miss:
            return f"UNACCOUNTED ({miss} of {len(urls)} not accounted)"
        if all(x == "captured" for x in state):
            return "captured page(s)"
        if "declared" in state:
            return "page(s), crawl declared"
        return "accepted target"

    out = {"project": p, "source": src, "total": len(locs),
           "localeUrls": len(locale_urls), "lang": a.lang,
           "families": {}, "expectedEntityCounts": {}, "unaccounted": {}}
    for fam, urls in sorted(fams.items(), key=lambda kv: -len(kv[1])):
        st = status(fam, urls)
        out["families"][fam] = {"count": len(urls), "status": st,
                                "urls": sorted(urls)[:400]}
        if fam in prefixes:
            out["expectedEntityCounts"][prefixes[fam]] = \
                out["expectedEntityCounts"].get(prefixes[fam], 0) + len(urls)
        if st.startswith("UNACCOUNTED"):
            out["unaccounted"][fam] = len(urls)
    op = f"{pp}/workflow-output/sitemap-urls.json"
    json.dump(out, open(op, "w"), indent=1, ensure_ascii=False)
    print(f"sitemap_enumerate: {out['total']} URL(s) from {src} "
          f"({out['localeUrls']} in locale {a.lang or 'all'}) -> {op}")
    for fam, info in list(out["families"].items())[:18]:
        print(f"  {info['count']:>5}  {fam[:46]:<46} {info['status']}")
    if out["expectedEntityCounts"]:
        print("  expected entity load counts: "
              + ", ".join(f"{k}={v}" for k, v in out["expectedEntityCounts"].items()))


if __name__ == "__main__":
    main()
