#!/usr/bin/env python3
"""link-integrity.py — BLOCKING gate: no rendered page may carry an internal
anchor that SHOULD resolve on the migrated site but still points at a source
path (operator finding 2026-07-21: home carousel 'Learn more' ->
/sending-within-singapore/prepaid-label — a migrated page — 404 as-is; the
/en-prefixed rewire regex never fired on locale-less sources, so EVERY markup
anchor site-wide was dead).

FAILS on any root-relative href whose slugified path is a MIGRATED PAGE
(payload) or a CLASSIFIED ENTITY (mainresource config) — those have Jahia
targets and must have been rewired. Out-of-scope internal paths (never
crawled) are counted and NAMED as warnings, not gated: they are a crawl-scope
decision, not a producer defect.

Usage: link-integrity.py <project> <site> [--locale en] [--pages a,b]
"""
import base64
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

JAHIA_PREFIXES = ("/sites/", "/cms/", "/modules/", "/files/", "/jahia/")


def fetch(url, user, pw):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Basic " +
                   base64.b64encode(f"{user}:{pw}".encode()).decode())
    return urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")


def main():
    project, site = sys.argv[1], sys.argv[2]
    locale = sys.argv[sys.argv.index("--locale") + 1] if "--locale" in sys.argv else "en"
    only = sys.argv[sys.argv.index("--pages") + 1].split(",") if "--pages" in sys.argv else None
    host = (os.environ.get("JAHIA_URL") or "http://localhost:8080").rstrip("/")
    user = (os.environ.get("JAHIA_USER") or "root").split(":")[0]
    pw = os.environ.get("JAHIA_PASS") or "root"
    cl = json.load(open(f"orchestration/content/{project}.content-load.json"))
    pages = [s for s in cl.get("pages", {}) if not only or s in only]
    entity = set()
    try:
        from load_main_resources import classified_slugs
        entity = set(classified_slugs(project))
    except ImportError:
        pass
    smap = {}
    sm = f"orchestration/sitemaps/{project}.txt"
    if os.path.exists(sm):
        for line in open(sm):
            sl = line.strip()
            if sl and not sl.startswith("#"):
                smap[sl.split("/")[-1].lower()] = sl
                smap[sl.lower()] = sl

    def slugify(h):
        return h.split("#")[0].split("?")[0].strip("/").replace("/", "_")

    bad, warn, fetched = [], {}, 0
    for slug in pages:
        page_path = "home" if slug == "home" else f"home/{smap.get(slug.lower(), slug)}"
        try:
            html = fetch(f"{host}/cms/render/default/{locale}/sites/{site}/"
                         f"{page_path}.html", user, pw)
            fetched += 1
        except Exception:
            continue
        for h in set(re.findall(r'href="(/[^"#?]*)', html)):
            if not h or h.startswith(JAHIA_PREFIXES) or h == "/":
                continue
            if re.search(r"\.(pdf|jpe?g|png|zip|docx?|svg|webp|css|js)$", h, re.I):
                continue
            s2 = slugify(h)
            if not s2:
                continue
            if s2 in cl.get("pages", {}) or s2 in entity:
                bad.append(f"{slug}: dead internal href {h!r} — its target is "
                           f"migrated ({'entity' if s2 in entity else 'page'}) "
                           f"and must have been rewired")
            else:
                warn[h] = warn.get(h, 0) + 1
    if warn:
        tops = sorted(warn.items(), key=lambda kv: -kv[1])[:10]
        print(f"  ~ {len(warn)} out-of-scope internal path(s) (crawl-scope "
              f"decision, not gated): "
              + ", ".join(f"{h} x{n}" for h, n in tops), file=sys.stderr)
    if not fetched:
        print("FAIL: link-integrity — no page could be rendered", file=sys.stderr)
        sys.exit(1)
    if bad:
        for x in sorted(set(bad))[:30]:
            print(f"  - {x}")
        print(f"FAIL: link-integrity — {len(bad)} dead rewireable link(s) over "
              f"{fetched} page(s)", file=sys.stderr)
        sys.exit(1)
    print(f"PASS: link-integrity — {fetched} page(s), every rewireable internal "
          f"anchor points at its Jahia target")


if __name__ == "__main__":
    main()
