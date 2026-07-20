#!/usr/bin/env python3
"""populate_chrome.py — the site chrome as EDITABLE Jahia content (2026-07-16).

The archetype model replaces the source's chrome markup with contributed
components; this step fills them from the captured source chrome
(workflow-output/chrome-capture.json, persisted by semanticize):

  siteHeader  <- logo image (DAM weakref) + TOP LINKS as sgp:cta children
                 (linkLabel editable; linkOrig keeps the live href until an
                 editor rewires via the Content Editor picker — rule 9)
  footer      <- link COLUMNS as sgp:cardItem children (column title +
                 sgp:cta children per link) + copyright line in body

Everything is a real node editors manage in Page Builder / jContent — the
mandate: no chrome text an editor cannot touch. Idempotent: skips nodes that
already have children. Breadcrumb needs no content (tree-driven view).

Usage: populate_chrome.py <project> <site> [--locale en]
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup  # noqa: E402
from load_content import Loader  # noqa: E402  (reuses MCP + upload_dam)


def _links(el, limit=12):
    """(label, href) pairs from anchors with visible text."""
    out = []
    for a_ in el.find_all("a", href=True):
        label = a_.get_text(" ", strip=True) or (a_.get("aria-label") or "").strip()             or (a_.get("title") or "").strip()             or ((a_.find("img").get("alt", "") if a_.find("img") else "")).strip()
        if label and len(label) <= 80 and a_["href"].rstrip("/") not in ("", "#"):
            out.append((label[:250], a_["href"]))
        if len(out) >= limit:
            break
    return out


def _mk_cta(ld, parent, name, label, href):
    try:
        ld.m.create(parent, f"{ld.ns}:cta", {"linkLabel": label, "linkOrig": href},
                    name=name, locale=ld.locale)
        return True
    except Exception as e:
        print(f"  ! cta {name}: {str(e)[:100]}", file=sys.stderr)
        return False


def populate_header(ld, html):
    base = f"/sites/{ld.site}/home/header/siteHeader"
    try:
        node = ld.m.get(base, locale=ld.locale)
    except Exception:
        print("  = no siteHeader node — skipped")
        return
    try:
        kids = ld.m.gql('query{jcr(workspace:EDIT){nodeByPath(path:"%s")'
                        '{children{nodes{name}}}}}' % base)
        if (kids.get("jcr", {}).get("nodeByPath", {}) or {}).get("children", {}).get("nodes"):
            print("  = siteHeader already populated — skipped")
            return
    except Exception:
        pass
    soup = BeautifulSoup(html, "lxml")
    # logo: first img whose src/alt smells like a logo, else the first img
    logo = next((i for i in soup.find_all("img")
                 if re.search(r"logo", (i.get("src", "") + " " + i.get("alt", "")), re.I)),
                soup.find("img"))
    if logo is not None:
        fname = os.path.basename((logo.get("src") or "").split("?")[0])
        dam = ld.upload_dam(fname) if fname else None
        if dam:
            try:
                ld.m.update(base, {"image": dam.get("path") or dam["uuid"]},
                            locale=ld.locale)
                print(f"  + siteHeader logo <- {fname}")
            except Exception as e:
                print(f"  ! logo weakref: {str(e)[:100]}", file=sys.stderr)
    # top links: nav-ish anchors before the main menu (utility bar)
    seen, n = set(), 0
    for label, href in _links(soup):
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        n += 1
        _mk_cta(ld, base, f"top-link-{n}", label, href)
        if n >= 8:
            break
    print(f"  + siteHeader: {n} top link(s)")


_SOCIAL_NAME = re.compile(
    r"(facebook|instagram|linkedin|youtube|twitter|x\.com|tiktok)", re.I)


def populate_footer(ld, html):
    base = f"/sites/{ld.site}/home/footer/footer"
    try:
        ld.m.get(base, locale=ld.locale)
    except Exception:
        print("  = no footer node — skipped")
        return
    # ADDITIVE idempotency (hollow-footer class, 2026-07-20): skip only the
    # named children that already exist — a partially populated footer (cols
    # created, social/legal added later by a harness fix) must complete, not
    # freeze at whatever the first run produced.
    existing = set()
    try:
        kids = ld.m.gql('query{jcr(workspace:EDIT){nodeByPath(path:"%s")'
                        '{children{nodes{name}}}}}' % base)
        existing = {n["name"] for n in ((kids.get("jcr", {}).get("nodeByPath", {}) or {})
                                        .get("children", {}) or {}).get("nodes") or []}
    except Exception:
        pass
    soup = BeautifulSoup(html, "lxml")
    # SINGLE SOURCE OF TRUTH: the site inventory already extracted the footer
    # columns (heading-titled AND heading-less footers); consume it, never
    # re-parse with weaker heuristics (stellar-core Phase 1 artifact)
    cols, ncol = [], 0
    inv_ftr = {}
    inv_p = f"projects/{ld.project}/workflow-output/site-inventory.json"
    try:
        inv_ftr = ((json.load(open(inv_p)).get("chrome") or {}).get("footer") or {})
        for i, c in enumerate(inv_ftr.get("columns") or [], 1):
            cols.append((c.get("title") or f"Links {i}",
                         [(l["label"], l["href"]) for l in c.get("links") or []]))
    except (FileNotFoundError, ValueError):
        pass
    if not cols:
        for el in soup.find_all(True):
            heading = el.find(["h2", "h3", "h4", "h5", "h6", "strong"])
            links = _links(el, limit=8)
            if heading is not None and 2 <= len(links) <= 8 and el.parent is not None:
                title = heading.get_text(" ", strip=True)[:250]
                if title and all(title != c[0] for c in cols):
                    cols.append((title, links))
            if len(cols) >= 6:
                break

    def _mk_col(cname, title, links):
        nonlocal ncol
        if cname in existing:
            return
        try:
            ld.m.create(base, f"{ld.ns}:cardItem", {"jcr:title": title},
                        name=cname, locale=ld.locale)
        except Exception as e:
            print(f"  ! footer col {title!r}: {str(e)[:100]}", file=sys.stderr)
            return
        ncol += 1
        for i, (label, href) in enumerate(links, 1):
            _mk_cta(ld, f"{base}/{cname}", f"link-{i}", label, href)

    for i, (title, links) in enumerate(cols, 1):
        _mk_col(f"col-{i}", title, links)
    # social row: platform links render as labelled ctas (icon links carry no
    # text in the source — derive the platform name so editors see real labels)
    social = [(_SOCIAL_NAME.search(l["href"]).group(1).replace(".com", "").capitalize(),
               l["href"])
              for l in inv_ftr.get("social") or [] if _SOCIAL_NAME.search(l["href"])]
    if social:
        _mk_col("social", "", social)
    # legal bar: Sitemap / Terms / Privacy / ... — every chrome link editable
    legal = [(l["label"], l["href"]) for l in inv_ftr.get("legal") or [] if l.get("label")]
    if legal:
        _mk_col("legal", "", legal)
    # copyright: the shortest bottom-ish © text
    cr = next((t.strip() for t in soup.stripped_strings
               if "©" in t or "copyright" in t.lower()), "")
    if cr:
        try:
            ld.m.update(base, {"body": f"<p>{cr[:500]}</p>"}, locale=ld.locale)
        except Exception as e:
            print(f"  ! copyright: {str(e)[:100]}", file=sys.stderr)
    print(f"  + footer: {ncol} new column(s) (had {len(existing)})"
          f"{' + copyright' if cr else ''}")


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: populate_chrome.py <project> <site> [--locale en]")
    project, site = sys.argv[1], sys.argv[2]
    locale = sys.argv[sys.argv.index("--locale") + 1] if "--locale" in sys.argv else "en"
    cap_p = f"projects/{project}/workflow-output/chrome-capture.json"
    try:
        cap = json.load(open(cap_p))
    except (FileNotFoundError, ValueError):
        sys.exit(f"FAIL: {cap_p} missing (run semanticize first)")
    ld = Loader(project, site, locale=locale)
    ld.ns = (ld.manifest.get("passthroughType") or "ns:x").split(":")[0]
    ld.locale = locale
    hdr = cap.get("header") or cap.get("chrome") or ""
    ftr = cap.get("footer") or ""
    if hdr:
        populate_header(ld, hdr)
    if ftr:
        populate_footer(ld, ftr)
    for p in (f"/sites/{site}/home/header", f"/sites/{site}/home/footer"):
        try:
            ld.m.publish(p, languages=(locale, "fr"))
        except Exception:
            pass
    print("populate_chrome: done")


if __name__ == "__main__":
    main()
