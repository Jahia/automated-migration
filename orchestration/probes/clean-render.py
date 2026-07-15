#!/usr/bin/env python3
"""clean-render.py — assert every rendered page is free of source-junk.

THE gate the SingPost audit was missing (2026-07-15): structure gates pass a
site whose rendered pages still carry the source's cookie-consent banner,
notification carousel, SPA hydration islands and framework attrs — junk that is
not contributed content and that editors cannot remove. This probe measures the
ARTIFACT itself (no proxies):

  1. enumerates every jnt:page of the site from the JCR (never a file list),
  2. fetches each page's rendered HTML in BOTH workspaces (default + live),
  3. fails on ANY match of the junk patterns below (with file:page:pattern),
  4. archetype model only: fails if any page still owns a `shell` rawHtml blob
     node (the captured source body — jContent junk even when unrendered).

Usage: clean-render.py <siteKey> [--model archetype]
Env:   JAHIA_URL (default http://localhost:8080), JAHIA_USER/JAHIA_PASS (root/root)
Exit:  0 clean, 1 junk found (report on stdout).
"""
import json
import os
import re
import sys
import urllib.request

BASE = os.environ.get("JAHIA_URL", "http://localhost:8080")
USER = os.environ.get("JAHIA_USER", "root")
PASS = os.environ.get("JAHIA_PASS", "root")

JUNK = {
    "source-spa-island": r"astro-island|renderer-url=|component-url=",
    "framework-attrs": r"data-astro-cid",
    "cookie-consent": r"__tcfapi|cookiebot|onetrust|usercentrics|We value your privacy"
                      r"|Reject Non-Essential|Manage Preferences",
    "source-spa-script": r"runtime-assets/[a-f0-9]{16,}\.js",
    "source-nav": r"group/navigation-menu",
}


def http(url, data=None, headers=None):
    import base64
    req = urllib.request.Request(url, data=data, headers=headers or {})
    req.add_header("Authorization", "Basic " +
                   base64.b64encode(f"{USER}:{PASS}".encode()).decode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def gql(query):
    return json.loads(http(f"{BASE}/modules/graphql",
                           data=json.dumps({"query": query}).encode(),
                           headers={"Content-Type": "application/json",
                                    "Origin": BASE}))


def site_pages(site):
    q = ('{jcr(workspace:EDIT){nodesByQuery(query:"SELECT * FROM [jnt:page] AS p '
         f"WHERE ISDESCENDANTNODE(p,'/sites/{site}')\",queryLanguage:SQL2,limit:500)"
         '{nodes{path}}}}')
    d = gql(q)
    paths = [n["path"] for n in d["data"]["jcr"]["nodesByQuery"]["nodes"]]
    return [f"/sites/{site}/home"] + sorted(paths)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: clean-render.py <siteKey> [--model archetype]")
    site = sys.argv[1]
    archetype = "--model" in sys.argv and "archetype" in sys.argv
    pages = site_pages(site)
    failures = []
    checked = 0
    for ws in ("default", "live"):
        for p in pages:
            rel = p[len(f"/sites/{site}/"):]
            url = f"{BASE}/cms/render/{ws}/en/sites/{site}/{rel}.html"
            try:
                h = http(url)
            except Exception as e:
                # live may lag behind during the process — a fetch error is only
                # fatal in default (the workspace the loader just wrote)
                if ws == "default":
                    failures.append((ws, rel, "fetch-error", str(e)[:80]))
                continue
            checked += 1
            for kind, rx in JUNK.items():
                m = re.search(rx, h, re.I)
                if m:
                    failures.append((ws, rel, kind, m.group(0)[:60]))
    # archetype: no shell blob nodes in the JCR
    if archetype:
        d = gql('{jcr(workspace:EDIT){nodesByQuery(query:"SELECT * FROM [nt:base] AS n '
                f"WHERE ISDESCENDANTNODE(n,'/sites/{site}') AND NAME(n)='shell'\","
                'queryLanguage:SQL2,limit:50){nodes{path primaryNodeType{name}}}}}')
        for n in d["data"]["jcr"]["nodesByQuery"]["nodes"]:
            failures.append(("EDIT", n["path"], "shell-blob-node", n["primaryNodeType"]["name"]))
    print(json.dumps({"pages_checked": checked, "failures":
                      [{"ws": w, "page": p, "kind": k, "match": m}
                       for w, p, k, m in failures[:40]],
                      "failure_count": len(failures)}, indent=1))
    if failures:
        print(f"FAIL: clean-render — {len(failures)} junk finding(s) across "
              f"{checked} rendered page(s)", file=sys.stderr)
        sys.exit(1)
    print(f"PASS: clean-render — {checked} rendered page(s) free of source junk"
          + (", no shell blob nodes" if archetype else ""))


if __name__ == "__main__":
    main()
