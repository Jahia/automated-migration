#!/usr/bin/env python3
"""content-gap-sweep.py — NAMED per-page content-gap ledger (operator mandate
2026-07-17: 'missing content in pages... analyse' — floors tolerate misses and
h1-h3+images don't cover what a reviewer sees; this sweep names every gap).

For every migrated page, compare the HYDRATED MIRROR (source truth) against
the RENDERED EDIT PREVIEW at full granularity:
  - headings h1-h6 (exact text, chrome excluded)
  - images (hashed mirror basenames — the DAM upload dedupes by that name)
  - visible words (>=4 chars, set containment; chrome/consent excluded)
Writes workflow-output/content-gaps.json and prints the named gaps.
Measurement only — exit 0 always (the ledger drives fixes; inventory-coverage
stays the blocking floor gate).

Usage: content-gap-sweep.py <project> <site> [--pages a,b]
"""
import base64
import json
import re
import sys
import urllib.request

from bs4 import BeautifulSoup

REPO = "."
CHROME_TAGS = ("header", "footer", "nav")
CHROME_HINTS = ("consent", "cookie", "notification", "breadcrumb", "onetrust")


# chrome ISLAND components the pipeline REPLACES with Jahia chrome (nav, tools
# dropdown, toast, announcements/notification bar, search overlay) — their
# content is excluded BY DESIGN, symmetric with reconciliation/site_inventory.
_CHROME_ISLANDS = re.compile(r"(Navbar|ToolsDropdown|sonner|Announce|Notification|Search|MegaMenu)",
                             re.I)
_CONSENT_RX = re.compile(r"We value your privacy|Reject Non-Essential|cookiebot|onetrust", re.I)


def visible_soup(html):
    soup = BeautifulSoup(html, "lxml")
    for t in soup.find_all(["script", "style", "noscript", "template"]):
        t.decompose()
    for t in soup.find_all(CHROME_TAGS):
        t.decompose()
    for t in soup.find_all("astro-island"):
        if _CHROME_ISLANDS.search(t.get("component-url") or ""):
            t.decompose()
    for t in soup.find_all(True, class_=lambda c: c and any(
            h in " ".join(c).lower() for h in CHROME_HINTS)):
        t.decompose()
    # source SEARCH OVERLAY (chrome by design — Jahia chrome replaces it):
    # anchored on its close button, remove the containing panel
    for el in soup.find_all(True, id=re.compile(r"close-search|search-overlay", re.I)):
        panel = el
        for _ in range(4):
            if panel.parent is not None and getattr(panel.parent, "name", None) not in (None, "body", "html"):
                panel = panel.parent
        panel.decompose()
    # source SUBSITE NAV (e.g. the corporate section's own About Us/IR/... menu,
    # server-rendered outside <nav>): list-of-links blocks where >=80% of the
    # text is anchor text and >=4 links — navigation chrome, replaced by design.
    # NOTE (IA finding, 2026-07-17): the source HAS section-local navs; whether
    # to model them is an operator decision — reported, not improvised.
    for ul in soup.find_all("ul"):
        links = ul.find_all("a")
        txt = ul.get_text(" ", strip=True)
        atxt = " ".join(a2.get_text(" ", strip=True) for a2 in links)
        if len(links) >= 4 and txt and len(atxt) >= 0.8 * len(txt):
            ul.decompose()
    # consent overlay (script-injected, obfuscated classes): anchor on its own
    # text, climb to the container holding the action buttons, remove it
    for txt in soup.find_all(string=_CONSENT_RX):
        el = getattr(txt, "parent", None)
        cand = None
        for _ in range(6):
            if el is None or getattr(el, "name", None) in (None, "body", "html"):
                break
            if len(el.find_all("button")) >= 2 or _CONSENT_RX.search(el.get_text(" ", strip=True) or ""):
                cand = el
            el = el.parent
        try:
            if cand is not None:
                cand.decompose()
        except Exception:
            pass
    return soup


def page_facts(html):
    soup = visible_soup(html)
    heads = [h.get_text(" ", strip=True) for tag in ("h1", "h2", "h3", "h4", "h5", "h6")
             for h in soup.find_all(tag) if h.get_text(strip=True)]
    imgs = {(m.get("src") or "").split("?")[0].split("/")[-1]
            for m in soup.find_all("img") if m.get("src")}
    imgs = {i for i in imgs if re.match(r"^[a-f0-9]{12,}\.\w{2,4}$", i)}
    words = set(re.findall(r"[^\W\d_]{4,}", soup.get_text(" ", strip=True).lower()))
    return heads, imgs, words


def fetch(url, user, pw):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Basic " +
                   base64.b64encode(f"{user}:{pw}".encode()).decode())
    return urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")


def main():
    import os
    project, site = sys.argv[1], sys.argv[2]
    only = None
    if "--pages" in sys.argv:
        only = sys.argv[sys.argv.index("--pages") + 1].split(",")
    host = (os.environ.get("JAHIA_URL") or "http://localhost:8080").rstrip("/")
    user = (os.environ.get("JAHIA_USER") or "root").split(":")[0]
    pw = os.environ.get("JAHIA_PASS") or "root"
    cl = json.load(open(f"orchestration/content/{project}.content-load.json"))
    pages = [s for s in cl.get("pages", {}) if not only or s in only]
    ledger, tot_missing = {}, 0
    for slug in pages:
        mp = f"projects/{project}/workflow-output/local-mirror/{slug}.html"
        try:
            mirror = open(mp, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        # sitemap-aware path (2026-07-20): nested pages (sending/delivery-rates)
        # 404 on flat home/{slug} — same resolver rule as groundtruth_probe
        sm = f"orchestration/sitemaps/{project}.txt"
        smap = {}
        if os.path.exists(sm):
            for line in open(sm):
                sl = line.strip()
                if not sl or sl.startswith("#"):
                    continue
                smap[sl.split("/")[-1].lower()] = sl
                smap[sl.lower()] = sl
        page_path = "home" if slug == "home" else f"home/{smap.get(slug.lower(), slug)}"
        try:
            rendered = fetch(f"{host}/cms/render/default/en/sites/{site}/{page_path}.html",
                             user, pw)
        except Exception as e:
            ledger[slug] = {"error": str(e)[:120]}
            continue
        mh, mi, mw = page_facts(mirror)
        rh, ri, rw = page_facts(rendered)
        missing_heads = [h for h in mh if h not in rh]
        missing_imgs = sorted(mi - ri)
        missing_words = sorted(mw - rw)
        entry = {"missingHeadings": missing_heads,
                 "missingImages": missing_imgs,
                 "missingWords": missing_words[:60],
                 "mirror": {"headings": len(mh), "images": len(mi), "words": len(mw)}}
        ledger[slug] = entry
        n = len(missing_heads) + len(missing_imgs) + len(missing_words)
        tot_missing += n
        if n:
            print(f"== {slug}: {len(missing_heads)} heading(s), "
                  f"{len(missing_imgs)} image(s), {len(missing_words)} word(s) missing")
            for h in missing_heads[:5]:
                print(f"   H: {h[:90]}")
            for i in missing_imgs[:5]:
                print(f"   I: {i}")
            if missing_words:
                print(f"   W: {' '.join(missing_words[:15])}")
    out = f"projects/{project}/workflow-output/content-gaps.json"
    json.dump({"project": project, "pages": ledger},
              open(out, "w"), indent=1, ensure_ascii=False)
    clean = sum(1 for v in ledger.values() if not v.get("error")
                and not (v["missingHeadings"] or v["missingImages"] or v["missingWords"]))
    print(f"\ncontent-gap-sweep: {clean}/{len(ledger)} pages fully covered -> {out}")


if __name__ == "__main__":
    main()
