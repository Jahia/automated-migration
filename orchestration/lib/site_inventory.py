#!/usr/bin/env python3
"""site_inventory.py — the DETERMINISTIC site analysis (stellar-core Phase 1).

One pass over the wget mirror producing site-inventory.json: the COMPLETE
checklist of what the source site contains, which every later phase must
account for (inventory-coverage gate). Extraction only — no synthesis, no
vision, no LLM; every fact carries evidence (page + landmark/selector). What
this fixes (2026-07-16 retrospective): discovery classified region NAMES and
lifted text blindly; the operator kept finding what a DOM parse would have
found — logo, menu, breadcrumb, footer columns, repetition, card anatomy.

Semantic partition uses the browser's OWN vocabulary — ARIA landmarks and
HTML5 sectioning (<header>/<nav>/<main>/<footer>, role=banner|navigation|
main|contentinfo) — plus structured data the page EMBEDS (JSON-LD, OpenGraph,
framework island props via extract_nav's decoder).

Output: projects/<p>/workflow-output/site-inventory.json
  chrome:  header {logo, topLinks, search}, nav {menuTree source}, footer
           {columns, social, copyright}, excluded {consent, notifications}
  pages:   per slug: title/meta/og + REGIONS (top-level blocks of <main>):
           anatomy {headings, textChars, images, links, buttons, forms,
           tables, videos}, repetition {signature,count}, entitySignals,
           classes {root}
  theme:   dominant colors + font families from the mirrored stylesheets
  assets:  image inventory (file -> role guess, pages seen)

Usage: site_inventory.py <project> [--host HOST]
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup  # noqa: E402
from extract_nav import astro_nav, dom_nav, internal_slug  # noqa: E402

IMG_EXT = r"\.(png|jpe?g|gif|webp|svg|avif)"


def _soup(path):
    return BeautifulSoup(open(path, encoding="utf-8", errors="ignore").read(), "lxml")


def _vis(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def _file(src):
    f = os.path.basename((src or "").split("?")[0])
    return f if re.search(IMG_EXT + "$", f, re.I) else None


def _links(el, host, limit=40):
    out = []
    for a in el.find_all("a", href=True)[:limit * 2]:
        label = _vis(a) or (a.get("aria-label") or "").strip()             or (a.get("title") or "").strip()             or ((a.find("img") or {}).get("alt", "") if a.find("img") else "").strip()
        if not label or len(label) > 90 or a["href"].rstrip("/") in ("", "#"):
            continue
        out.append({"label": label[:120], "href": a["href"],
                    "internal": internal_slug(a["href"], host) is not None})
        if len(out) >= limit:
            break
    return out


def _landmark(soup, names, roles):
    """First matching landmark element: HTML5 tag OR ARIA role — the browser's
    own semantic vocabulary, no heuristics."""
    for n in names:
        el = soup.find(n)
        if el is not None:
            return el, f"<{n}>"
    for r in roles:
        el = soup.find(attrs={"role": r})
        if el is not None:
            return el, f"role={r}"
    return None, None


def chrome_inventory(soup, host, raw_html=""):
    ch = {}
    header, ev = _landmark(soup, ["header"], ["banner"])
    if header is not None:
        logo = next((i for i in header.find_all("img")
                     if re.search(r"logo", (i.get("src", "") + " " + i.get("alt", "")), re.I)),
                    header.find("img"))
        nav_in_header = header.find("nav")
        top_scope = header
        if nav_in_header is not None:
            # utility links = header links OUTSIDE the main nav
            for a in nav_in_header.find_all("a"):
                a["data-in-nav"] = "1"
        top = [l for l in _links(top_scope, host, limit=12)]
        ch["header"] = {
            "evidence": ev,
            "logo": ({"src": logo.get("src", ""), "alt": logo.get("alt", ""),
                      "file": _file(logo.get("src"))} if logo is not None else None),
            "topLinks": top,
            "search": bool(header.find("input", attrs={"type": "search"})
                           or header.find(attrs={"role": "search"})
                           or re.search(r"search", str(header), re.I)),
        }
    ast = astro_nav(raw_html) if raw_html else []
    nav_items = ast or dom_nav(str(soup))
    ch["nav"] = {"present": bool(nav_items),
                 "source": "astro-island navItems" if ast else "nav DOM",
                 "l1Count": len(nav_items or [])}
    bc, ev = _landmark(soup, [], [])
    bc_el = soup.find(attrs={"aria-label": re.compile("breadcrumb", re.I)}) \
        or soup.find(class_=re.compile("breadcrumb", re.I))
    ch["breadcrumb"] = {"present": bc_el is not None}
    footer, ev = _landmark(soup, ["footer"], ["contentinfo"])
    if footer is not None:
        cols = []
        # pass 1: heading-titled column blocks
        for el in footer.find_all(True):
            h = el.find(["h2", "h3", "h4", "h5", "h6", "strong"])
            links = _links(el, host, limit=10)
            if h is not None and 2 <= len(links) <= 10:
                t = _vis(h)[:120]
                if t and all(t != c["title"] for c in cols):
                    cols.append({"title": t, "links": links})
            if len(cols) >= 8:
                break
        # pass 2 (heading-less footers, e.g. SingPost): repeated same-signature
        # sibling groups where each member is a link list — each member is a
        # column; the title is the member's first non-link text, if any
        if not cols:
            for parent in footer.find_all(True):
                sibs = parent.find_all(True, recursive=False)
                groups = {}
                for c in sibs:
                    groups.setdefault((c.name, tuple(sorted(c.get("class") or []))),
                                      []).append(c)
                for _sig, members in groups.items():
                    if len(members) >= 2 and all(len(m.find_all("a", href=True)) >= 2
                                                 for m in members):
                        for m in members:
                            first_txt = next((t.strip() for t in m.stripped_strings
                                              if t.strip()), "")
                            in_link = m.find("a") is not None and                                 first_txt == _vis(m.find("a"))
                            cols.append({"title": "" if in_link else first_txt[:120],
                                         "links": _links(m, host, limit=10)})
                        break
                if cols:
                    break
            # last resort: each <ul> with >=3 links is a column
            if not cols:
                for ul in footer.find_all(["ul", "ol"]):
                    links = _links(ul, host, limit=10)
                    if len(links) >= 3:
                        cols.append({"title": "", "links": links})
                    if len(cols) >= 6:
                        break
        social = [l for l in _links(footer, host, limit=30)
                  if re.search(r"facebook|instagram|linkedin|youtube|twitter|x\.com|tiktok",
                               l["href"], re.I)]
        cr = next((t.strip()[:300] for t in footer.stripped_strings
                   if "©" in t or "copyright" in t.lower()), "")
        ch["footer"] = {"evidence": ev, "columns": cols, "social": social, "copyright": cr}
    ch["excluded"] = {
        "cookieConsent": bool(re.search(r"ConsentPopup|onetrust|cookiebot|We value your privacy",
                                        str(soup), re.I)),
        "notifications": bool(re.search(r"HeaderAnnouncements|notification-bar", str(soup), re.I)),
    }
    return ch


def region_anatomy(el, host):
    heads = [{"level": h.name, "text": _vis(h)[:200]}
             for h in el.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]) if _vis(h)][:12]
    imgs = [{"file": _file(i.get("src")), "alt": (i.get("alt") or "")[:120]}
            for i in el.find_all("img") if _file(i.get("src"))][:20]
    links = _links(el, host, limit=20)
    # repetition: largest same-signature sibling group anywhere inside
    best_sig, best_n = None, 0
    for parent in el.find_all(True):
        groups = Counter()
        for c in parent.find_all(True, recursive=False):
            if c.get("class"):
                groups[(c.name, tuple(sorted(c.get("class"))))] += 1
        for sig, n in groups.items():
            if n > best_n and n >= 2:
                best_sig, best_n = sig, n
    dates = [t.get("datetime") or _vis(t) for t in el.find_all("time")][:6]
    if not dates:
        dates = re.findall(r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b",
                           _vis(el))[:6]
    return {
        "headings": heads,
        "textChars": len(_vis(el)),
        "images": imgs,
        "links": links[:12],
        "buttons": len(el.find_all("button")),
        "forms": len(el.find_all("form")),
        "tables": len(el.find_all("table")),
        "videos": len(el.find_all(["video", "iframe"])),
        "repetition": ({"signature": " ".join(best_sig[1])[:80], "count": best_n}
                       if best_n >= 2 else None),
        "entitySignals": {"dates": dates,
                          "detailLinks": sum(1 for l in links if l["internal"]) >= 3},
        "classes": {"root": " ".join(el.get("class") or [])[:120]},
    }


def page_inventory(path, host):
    soup = _soup(path)
    main, ev = _landmark(soup, ["main"], ["main"])
    scope = main if main is not None else soup.body
    if scope is None:
        return None
    # drop nested chrome from the scope copy
    for t in ("header", "nav", "footer"):
        for el in scope.find_all(t):
            el.extract()
    regions = []
    for el in scope.find_all(True, recursive=False):
        if _vis(el) or el.find("img"):
            regions.append(region_anatomy(el, host))
    og = soup.find("meta", property="og:image")
    md = soup.find("meta", attrs={"name": "description"})
    ld = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(s.string or "{}")
            ld.append(j.get("@type") or [x.get("@type") for x in j.get("@graph", [])][:3])
        except (ValueError, AttributeError):
            pass
    return {"title": _vis(soup.find("title"))[:200],
            "metaDescription": (md.get("content", "") if md else "")[:300],
            "ogImage": _file(og.get("content")) if og else None,
            "jsonLdTypes": ld[:5],
            "mainEvidence": ev or "body-fallback",
            "regions": regions}


def theme_from_css(mirror_assets):
    colors, fonts = Counter(), Counter()
    for css in glob.glob(os.path.join(mirror_assets, "*.css"))[:20]:
        s = open(css, encoding="utf-8", errors="ignore").read()
        for c in re.findall(r"#[0-9a-fA-F]{6}\b", s):
            colors[c.lower()] += 1
        for f in re.findall(r"font-family\s*:\s*([^;}{]+)", s):
            fam = f.split(",")[0].strip().strip("'\"")
            if fam and not fam.startswith("var("):
                fonts[fam] += 1
    return {"colors": [c for c, _ in colors.most_common(10)],
            "fonts": [f for f, _ in fonts.most_common(6)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--host")
    a = ap.parse_args()
    crawl = f"projects/{a.project}/.reference/cache/_crawl"
    hosts = a.host and [a.host] or sorted(os.listdir(crawl)) if os.path.isdir(crawl) else []
    if not hosts:
        sys.exit(f"FAIL: no crawl cache under {crawl}")
    host = hosts[0]
    base = os.path.join(crawl, host)
    pages_html = sorted(glob.glob(os.path.join(base, "**", "*.html"), recursive=True))
    if not pages_html:
        sys.exit(f"FAIL: no cached pages under {base}")

    inv = {"project": a.project, "host": host, "pages": {}, "assets": {"images": {}}}
    home = os.path.join(base, "index.html")
    home_path = home if os.path.isfile(home) else pages_html[0]
    inv["chrome"] = chrome_inventory(
        _soup(home_path), host,
        raw_html=open(home_path, encoding="utf-8", errors="ignore").read())
    for ph in pages_html:
        rel = os.path.relpath(ph, base)
        slug = "home" if rel == "index.html" else \
            re.sub(r"\.html$", "", rel).replace("/", "_")
        pi = page_inventory(ph, host)
        if pi:
            inv["pages"][slug] = pi
            for r in pi["regions"]:
                for im in r["images"]:
                    if im["file"]:
                        e = inv["assets"]["images"].setdefault(
                            im["file"], {"pages": [], "alt": im["alt"]})
                        if slug not in e["pages"]:
                            e["pages"].append(slug)
    inv["theme"] = theme_from_css(
        f"projects/{a.project}/workflow-output/local-mirror/assets")

    out = f"projects/{a.project}/workflow-output/site-inventory.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(inv, open(out, "w"), indent=1, ensure_ascii=False)
    ch = inv["chrome"]
    print(f"[site_inventory] {out}: {len(inv['pages'])} page(s), "
          f"logo={'yes' if (ch.get('header') or {}).get('logo') else 'NO'}, "
          f"nav L1={ch['nav']['l1Count']} ({ch['nav']['source']}), "
          f"footer cols={len((ch.get('footer') or {}).get('columns', []))}, "
          f"{len(inv['assets']['images'])} image(s), "
          f"theme colors={len(inv['theme']['colors'])}")


if __name__ == "__main__":
    main()
