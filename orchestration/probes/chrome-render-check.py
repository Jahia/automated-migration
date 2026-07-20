#!/usr/bin/env python3
"""chrome-render-check.py — BLOCKING gate: contributed chrome actually RENDERS.

Class caught 2026-07-20 (hollow footer): footer columns + cta children sat
complete in the JCR while the semantic card view silently dropped child nodes
— every measurement had a blind spot (content-gap-sweep excludes <footer> on
both sides BY DESIGN; inventory-coverage checks nodes EXIST, not that they
render). This gate closes it: the RENDERED page's header/footer must contain
every chrome item the site inventory extracted from the source.

Checks (rendered EDIT preview of home, authenticated):
  footer: every column title, every column link label, every legal link label,
          every social href, the copyright line
  header: a logo <img>, every top-link label

No thresholds, no proxies (operator doctrine): the ledger IS the source truth,
the render IS what visitors see. Exit 1 on any named miss.

Usage: chrome-render-check.py <project> <site> [--locale en]
"""
import base64
import json
import os
import re
import sys
import urllib.request

from bs4 import BeautifulSoup


def fetch(url, user, pw):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Basic " +
                   base64.b64encode(f"{user}:{pw}".encode()).decode())
    return urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def main():
    project, site = sys.argv[1], sys.argv[2]
    locale = sys.argv[sys.argv.index("--locale") + 1] if "--locale" in sys.argv else "en"
    host = (os.environ.get("JAHIA_URL") or "http://localhost:8080").rstrip("/")
    user = (os.environ.get("JAHIA_USER") or "root").split(":")[0]
    pw = os.environ.get("JAHIA_PASS") or "root"
    inv = json.load(open(f"projects/{project}/workflow-output/site-inventory.json"))
    ch = inv.get("chrome") or {}
    html = fetch(f"{host}/cms/render/default/{locale}/sites/{site}/home.html", user, pw)
    soup = BeautifulSoup(html, "lxml")
    misses = []

    ftr_inv = ch.get("footer") or {}
    footer = soup.find("footer")
    if ftr_inv and footer is None:
        misses.append("footer: <footer> element absent from rendered page")
    elif ftr_inv:
        ftxt = norm(footer.get_text(" ", strip=True))
        fhrefs = {a.get("href", "") for a in footer.find_all("a")}
        for c in ftr_inv.get("columns") or []:
            t = norm(c.get("title"))
            if t and t not in ftxt:
                misses.append(f"footer column title missing: {c['title']!r}")
            for l in c.get("links") or []:
                if norm(l.get("label")) and norm(l["label"]) not in ftxt:
                    misses.append(f"footer link missing: {l['label']!r} ({l['href']})")
        for l in ftr_inv.get("legal") or []:
            if norm(l.get("label")) and norm(l["label"]) not in ftxt:
                misses.append(f"footer legal link missing: {l['label']!r} ({l['href']})")
        for l in ftr_inv.get("social") or []:
            href = (l.get("href") or "").rstrip("/")
            if href and not any(h.rstrip("/").endswith(href.split("://")[-1])
                                or href.split("://")[-1] in h for h in fhrefs):
                misses.append(f"footer social link missing: {href}")
        cr = norm(ftr_inv.get("copyright"))
        if cr and cr not in ftxt:
            misses.append(f"footer copyright missing: {ftr_inv['copyright']!r}")

    hdr_inv = ch.get("header") or {}
    header = soup.find("header")
    if hdr_inv and header is None:
        misses.append("header: <header> element absent from rendered page")
    elif hdr_inv:
        htxt = norm(header.get_text(" ", strip=True))
        if hdr_inv.get("logo") and not header.find("img"):
            misses.append("header logo <img> missing from rendered header")
        for l in hdr_inv.get("topLinks") or []:
            if norm(l.get("label")) and norm(l["label"]) not in htxt:
                misses.append(f"header top link missing: {l['label']!r}")

    if misses:
        print(f"FAIL: chrome-render-check — {len(misses)} chrome item(s) in the "
              f"source ledger do not render:")
        for m in misses:
            print(f"  - {m}")
        sys.exit(1)
    ncol = len((ftr_inv.get("columns") or []))
    print(f"PASS: chrome-render-check — {ncol} footer column(s), legal bar, social, "
          f"copyright, header logo + top links all render")


if __name__ == "__main__":
    main()
