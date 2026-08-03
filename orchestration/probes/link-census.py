#!/usr/bin/env python3
"""link-census.py — every internal link must have a destination in the model.

A migrated card whose CTA points at nothing is the most visible possible defect, and
it is invisible to every other gate: `link-integrity.py` checks that hrefs whose
target IS migrated point at it, so a target that was never modelled at all passes
silently. Measured on salonphoto (2026-08-03): the home page's own hero carousel and
picture-grids linked to 10 distinct targets, and only ONE of them was a captured page
— the rest were entity details and a third ticketing URL nobody had decided about.
Corpus-wide: 147 links landed on captured pages, 83 on declared entity prefixes, and
**42 on nothing at all**.

Menu-scoped capture is correct (a BFS sample is the twice-burned failure), so
card-reached targets legitimately do not exist yet at census time. What is NOT
acceptable is not KNOWING about them. Every internal link target must therefore be
one of:
  1. a captured page (page-inventory slug),
  2. covered by a mainresource `urlPrefixes` entry (an entity to be loaded),
  3. a page slug declared in the sitemap (menu page, crawl pending),
  4. declared in scope-rules.json `pagesToCrawl` — a target the operator has decided
     IS a page, whose crawl is pending (the decision exists; the bytes don't yet),
  5. explicitly accounted for in scope-rules.json `acceptedTargets`
     (out-of-scope / external-platform / asset / broken source link), each with a reason.

Anything else FAILS, naming the target and the pages that link to it.

Usage: link-census.py <project> [--lang fr-FR] [--report]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

from bs4 import BeautifulSoup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--lang", default="")
    ap.add_argument("--report", action="store_true",
                    help="print the full classification, then still gate")
    a = ap.parse_args()
    p = a.project
    pp = f"projects/{p}"
    mirror = f"{pp}/workflow-output/local-mirror"
    if not os.path.isdir(mirror):
        sys.exit(f"FAIL link-census: no scoped mirror at {mirror}")

    inv = json.load(open(f"{pp}/workflow-output/page-inventory.json"))
    captured = {pg.get("slug") for pg in inv.get("pages", [])}
    host_re = re.compile(r"^https?://[^/]*" +
                         re.escape(re.sub(r"^https?://", "",
                                          (inv.get("siteUrl") or "")).split("/")[0]))

    prefixes = {}
    mrp = f"orchestration/content/{p}.mainresource.json"
    if os.path.exists(mrp):
        for key, f in (json.load(open(mrp)).get("folders") or {}).items():
            for pre in f.get("urlPrefixes") or []:
                prefixes[pre.strip("/")] = key

    sitemap = set()
    smp = f"orchestration/sitemaps/{p}.txt"
    if os.path.exists(smp):
        for line in open(smp, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                sitemap.add(line.split("/")[-1])

    accepted, to_crawl = {}, {}
    try:
        _sr = json.load(open(f"{pp}/workflow-output/scope-rules.json"))
        for t in (_sr.get("acceptedTargets") or []):
            accepted[str(t.get("path", "")).strip("/")] = t.get("reason", "")
        for t in (_sr.get("pagesToCrawl") or []):
            to_crawl[str(t.get("path", "")).strip("/")] = t.get("reason", "")
    except (OSError, ValueError):
        pass

    def norm(href):
        h = host_re.sub("", href)
        h = h.split("#")[0].split("?")[0]
        segs = [s for s in h.split("/") if s]
        if a.lang and segs and segs[0].lower() == a.lang.lower():
            segs = segs[1:]
        return "/".join(segs)

    kinds = Counter()
    unknown = defaultdict(set)
    for fn in sorted(f for f in os.listdir(mirror) if f.endswith(".html")):
        soup = BeautifulSoup(open(os.path.join(mirror, fn), encoding="utf-8",
                                 errors="replace").read(), "lxml")
        # WHOLE PAGE, not just <main>: the footer is chrome, but its links point at
        # real pages (legal, accessibility, sitemap). Scanning only <main> made this
        # gate report "every target accounted" while every footer destination was
        # invisible — a false green found by cross-checking against /sitemap.xml
        # (2026-08-03). Chrome links are still links.
        scope_el = soup.body or soup
        for anchor in scope_el.select("a[href]"):
            href = anchor["href"].strip()
            if href.startswith(("#", "mailto", "tel", "javascript")):
                continue
            # the source emits malformed absolutes (" https:/www.comexposium.com" —
            # leading space, single slash). Still external, not an internal path.
            if re.match(r"^https?:/", href) and not host_re.match(href):
                kinds["external"] += 1
                continue
            # SCHEME-LESS EXTERNALS (2026-08-03): article prose links out with a bare
            # domain (href="www.musee-marine.fr") or a bare address
            # (href="info@quaidelaphoto.fr"). Both are external, but a naive path
            # normalizer reads them as relative internal paths and demands a decision
            # for a museum's website. Only detail pages do this, so a menu-only corpus
            # never exposed it. A first segment that looks like a host (a dot plus a
            # 2-6 char TLD) or any '@' is external.
            _first = href.lstrip("/").split("/")[0]
            # a host needs only TWO labels (quaidelaphoto.fr), so match `label(.label)+`
            # and exclude file extensions — otherwise `sitemap.xml` would read as a host
            _FILE_EXT = {"pdf", "jpg", "jpeg", "png", "gif", "svg", "webp", "ico", "css",
                         "js", "json", "xml", "html", "htm", "zip", "doc", "docx", "xls",
                         "xlsx", "ppt", "pptx", "mp4", "mp3", "txt", "csv", "aspx"}
            _looks_host = (re.match(r"^([\w-]+\.)+[a-z]{2,10}$", _first, re.I)
                           and _first.rsplit(".", 1)[-1].lower() not in _FILE_EXT)
            if "@" in _first or _looks_host:
                kinds["external"] += 1
                continue
            target = norm(href)
            if not target:
                kinds["home"] += 1
                continue
            flat = target.replace("/", "_")
            if flat in captured:
                kinds["captured page"] += 1
            elif any(target.startswith(pre + "/") for pre in prefixes):
                kinds["entity (declared prefix)"] += 1
            elif flat in sitemap:
                kinds["menu page (crawl pending)"] += 1
            elif target in to_crawl or any(
                    target.startswith(k + "/") for k in to_crawl):
                kinds["page (crawl declared)"] += 1
            elif target in accepted or any(
                    target.startswith(k + "/") for k in accepted):
                kinds["accepted target"] += 1
            else:
                kinds["UNACCOUNTED"] += 1
                unknown[target].add(fn[:-5])

    if a.report:
        print("link census:")
        for k, v in kinds.most_common():
            print(f"  {v:>5}  {k}")

    if unknown:
        fam = defaultdict(list)
        for t in unknown:
            fam["/".join(t.split("/")[:2]) if "/" in t else t].append(t)
        print(f"FAIL link-census [{p}]: {kinds['UNACCOUNTED']} internal link(s) to "
              f"{len(unknown)} target(s) that are neither a captured page, a declared "
              f"entity prefix, a sitemap page, a declared page-to-crawl, nor an "
              f"accepted target")
        for g in sorted(fam, key=lambda g: -len(fam[g]))[:10]:
            ts = sorted(fam[g])
            src = sorted(unknown[ts[0]])[:2]
            print(f"  - [{len(ts):>2}] {g}   e.g. {ts[0][:60]}  <- {', '.join(src)}")
        print("  Fix: add the family to <project>.mainresource.json urlPrefixes (entity), "
              "crawl it as a page, or record it in scope-rules.json \"acceptedTargets\" "
              "with a reason.")
        sys.exit(1)
    total = sum(kinds.values())
    print(f"PASS link-census: {total} link(s) — "
          + ", ".join(f"{v} {k}" for k, v in kinds.most_common()))


if __name__ == "__main__":
    main()
