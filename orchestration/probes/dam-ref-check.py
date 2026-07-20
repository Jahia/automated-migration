#!/usr/bin/env python3
"""dam-ref-check.py — BLOCKING gate: every RASTER image a page serves must be
a Jahia Media-manager reference (/files/...), never a frozen module-static
asset (operator mandate 2026-07-20: observed bg-cover divs and 900+ inline
<img> rendering /modules/<m>/static/assets/... with no DAM presence — not
swappable in the editor, invisible to the Media manager).

Sweeps EVERY page's EDIT-preview render (the pipeline's render truth,
EDIT-only doctrine) and FAILS naming page + offending ref when a raster
/modules/*/static/assets/* URL survives in src, srcset or css url().
svg is exempt: icons are design assets shipped with the module, not media.

Usage: dam-ref-check.py <project> <site> [--locale en] [--pages a,b]
Exit 0 clean / 1 violations (named).
"""
import base64
import json
import os
import re
import sys
import urllib.request

RASTER_RE = re.compile(
    r"/modules/[^/\"'()\s]+/static/assets/"
    r"[A-Za-z0-9_.-]+\.(?:png|jpe?g|gif|webp|avif)", re.I)


def fetch(url, user, pw):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Basic " +
                   base64.b64encode(f"{user}:{pw}".encode()).decode())
    return urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")


def main():
    project, site = sys.argv[1], sys.argv[2]
    locale = sys.argv[sys.argv.index("--locale") + 1] if "--locale" in sys.argv else "en"
    only = None
    if "--pages" in sys.argv:
        only = sys.argv[sys.argv.index("--pages") + 1].split(",")
    host = (os.environ.get("JAHIA_URL") or "http://localhost:8080").rstrip("/")
    user = (os.environ.get("JAHIA_USER") or "root").split(":")[0]
    pw = os.environ.get("JAHIA_PASS") or "root"
    cl = json.load(open(f"orchestration/content/{project}.content-load.json"))
    pages = [s for s in cl.get("pages", {}) if not only or s in only]
    if not pages:
        print("FAIL: dam-ref-check — no pages to sweep (a gate that cannot "
              "measure must fail)", file=sys.stderr)
        sys.exit(1)
    smap = {}
    sm = f"orchestration/sitemaps/{project}.txt"
    if os.path.exists(sm):
        for line in open(sm):
            sl = line.strip()
            if not sl or sl.startswith("#"):
                continue
            smap[sl.split("/")[-1].lower()] = sl
            smap[sl.lower()] = sl
    bad, fetched, errors = [], 0, []
    for slug in pages:
        page_path = "home" if slug == "home" else f"home/{smap.get(slug.lower(), slug)}"
        try:
            html = fetch(f"{host}/cms/render/default/{locale}/sites/{site}/"
                         f"{page_path}.html", user, pw)
            fetched += 1
        except Exception as e:
            errors.append(f"{slug}: {str(e)[:100]}")
            continue
        refs = sorted(set(RASTER_RE.findall(html)))
        for r in refs[:5]:
            bad.append(f"{slug}: serves module-static raster {r}")
        if len(refs) > 5:
            bad.append(f"{slug}: ... and {len(refs) - 5} more static raster ref(s)")
    if errors:
        for e in errors[:10]:
            print(f"  ! unreadable: {e}", file=sys.stderr)
    if not fetched:
        print("FAIL: dam-ref-check — no page could be rendered", file=sys.stderr)
        sys.exit(1)
    if bad:
        for x in bad[:40]:
            print(f"  - {x}")
        print(f"FAIL: dam-ref-check — {len(bad)} violation(s) over {fetched} page(s)",
              file=sys.stderr)
        sys.exit(1)
    print(f"PASS: dam-ref-check — {fetched} page(s), every raster image is a "
          f"Media-manager reference (svg module icons exempt)")


if __name__ == "__main__":
    main()
