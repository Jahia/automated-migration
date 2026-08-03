#!/usr/bin/env python3
"""extract_nav.py — extract the SOURCE SITE'S REAL navigation IA (deterministic).

The page tree drives the Jahia nav (rule 19), so the page tree must mirror the
source's INFORMATION ARCHITECTURE — not the crawl's URL sample (2026-07-15
SingPost lesson: the crawl-URL fallback produced an L1 of business/corporate/…
while the site's real L1 menu is Sending/Receiving/Shop/Pay/Document Services/
Money & Health Insurance).

Reads the cached home page and parses the navigation structure out of the
captured markup. Two strategies, first hit wins:
  1. astro-island props carrying `navItems` (label/href/subMenu JSON — the
     Astro/Drupal pattern; the FULL menu rides serialized props)
  2. the <nav> DOM itself: nested <ul>/<li>/<a> lists (generic fallback)

Writes (consumed by build_nav_tree / create_pages / load_content):
  orchestration/sitemaps/<project>.txt          nested rel paths, menu order,
                                                leaf == the crawl's flat slug
                                                ('_'-joined URL segments)
  orchestration/sitemaps/<project>.labels.json  leaf-slug -> clean menu label

`--urls` prints the menu's internal hrefs (one per line, locale prefix intact)
and writes nothing — this is the mode nav_scope_crawl consumes to derive the
menu-scoped crawl list. `--lang <prefix>` strips a locale path segment
(`/fr-FR/salon` -> `salon`) so sitemap leaves match the crawler's own slugs.

Usage: extract_nav.py <project> [--home <cached-home.html>] [--max-depth 3]
                      [--lang fr-FR] [--urls]
Exit 0 with a report; exit 1 if no nav structure could be extracted.
"""
import argparse
import glob
import html as htmllib
import json
import os
import re
import sys


def _dec(v):
    """Decode one astro-island serialized value: [0, x] = plain (x may be an
    object whose values are themselves encoded), [1, [..]] = array of encoded.
    A bare [0] (no value) is the empty marker (e.g. "subMenu":[0]) -> None."""
    if not isinstance(v, list):
        return v
    if len(v) == 1:
        return None
    if len(v) != 2:
        return v
    tag, val = v
    if tag == 0:
        if isinstance(val, dict):
            return {k: _dec(x) for k, x in val.items()}
        return val
    if tag == 1:
        return [_dec(x) for x in (val or [])]
    return val


def astro_nav(page_html):
    """navItems from an astro-island props attribute; [] when absent.

    QUOTE TRAP (2026-07-20, the three-section miss): Astro serializes island
    attributes with SINGLE quotes when the JSON contains double quotes
    (props='{"navItems":...}') — the double-quote-only regex never read the
    real Navbar island, so the PERSONAL/BUSINESS/ENTERPRISE section wrapper
    was invisible and the site was modeled on one section's menu. Match both."""
    pats = (r"<astro-island[^>]*\sprops=\"([^\"]*)\"",
            r"<astro-island[^>]*\sprops='([^']*)'")
    best = []
    for pat in pats:
        for m in re.finditer(pat, page_html):
            raw = htmllib.unescape(m.group(1))
            if '"navItems"' not in raw:
                continue
            try:
                props = json.loads(raw)
            except ValueError:
                continue
            items = _dec(props.get("navItems", [1, []]))
            if items and len(json.dumps(items)) > len(json.dumps(best)):
                best = items  # keep the RICHEST navItems (the full Navbar)
    return best


def section_navs(items):
    """Split a section-wrapper navItems ([{label:PERSONAL, subMenu:[...]},
    {label:BUSINESS,...}]) into {section_label: menu_items}. Detection: every
    top entry has a subMenu and no own href — plain menus return {} (single-
    tree sites keep the old shape untouched)."""
    if not items or not all(isinstance(x, dict) for x in items):
        return {}
    if all((x.get("subMenu") and not (x.get("href") or "").strip("/#"))
           for x in items):
        return {(x.get("label") or f"section-{i}"): x.get("subMenu") or []
                for i, x in enumerate(items)}
    return {}


def dom_nav(page_html):
    """Generic fallback: deepest <nav> with nested lists -> [{label,href,subMenu}]."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    soup = BeautifulSoup(page_html, "lxml")
    best, best_n = None, 0
    for nav in soup.find_all("nav"):
        n = len(nav.find_all("a", href=True))
        if n > best_n:
            best, best_n = nav, n

    def walk(ul):
        out = []
        for li in ul.find_all("li", recursive=False):
            a = li.find("a", href=True) or li.find(["a", "button", "span"])
            if not a:
                continue
            label = a.get_text(" ", strip=True)
            href = a.get("href") if a.name == "a" else "#"
            sub = li.find(["ul", "ol"])
            out.append({"label": label, "href": href or "#",
                        "subMenu": walk(sub) if sub else []})
        return out

    if not best:
        return []
    top = best.find(["ul", "ol"])
    return walk(top) if top else []


def slugify(label):
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return s or "section"


def internal_slug(href, host, lang=""):
    """menu href -> the crawl's flat slug ('_'-joined segments); None if external.

    `lang` drops a leading locale segment so the slug matches what crawl-site.py
    --lang produced (/fr-FR/salon -> 'salon', not 'fr-FR_salon'). Without this the
    sitemap and the capture disagree on every page's identity."""
    if not href or href in ("#", "/"):
        return None
    href = re.sub(r"^https?://" + re.escape(host), "", href)
    if re.match(r"^(https?:)?//|^mailto:|^tel:", href):
        return None  # external
    segs = [s for s in href.split("?")[0].split("#")[0].split("/") if s]
    if lang and segs and segs[0].lower() == lang.lower():
        segs = segs[1:]
    return "_".join(segs) if segs else None


def internal_hrefs(items, host, out=None):
    """Every internal href in the menu tree, in menu order, verbatim (locale
    prefix intact) — the crawl list nav_scope_crawl feeds to crawl-site.py."""
    out = [] if out is None else out
    for it in items or []:
        if not isinstance(it, dict):
            continue
        h = (it.get("href") or "").split("#")[0].split("?")[0]
        if h and h not in ("#", "/") and not re.match(
                r"^(https?:)?//|^mailto:|^tel:", re.sub(r"^https?://" + re.escape(host), "", h)):
            h = re.sub(r"^https?://" + re.escape(host), "", h)
            if h.startswith("/") and h.rstrip("/") not in out:
                out.append(h.rstrip("/"))
        internal_hrefs(it.get("subMenu"), host, out)
    return out


def resolve_home(project, explicit=None):
    """(path, host) of the cached home page.

    The page INVENTORY is authoritative: crawl-site.py records slug 'home' and
    its cachedAt path, whatever the URL shape (a locale-prefixed source caches
    as `<host>/fr-FR.html`, never `<host>/index.html` — the glob-only lookup
    missed it and reported "no cached home page" on a perfectly good capture).
    Falls back to the historical globs for pre-inventory captures."""
    base = f"projects/{project}"
    if explicit:
        host = os.path.basename(os.path.dirname(explicit))
        return explicit, host
    try:
        inv = json.load(open(f"{base}/workflow-output/page-inventory.json"))
        host = re.sub(r"^https?://", "", (inv.get("siteUrl") or "")).split("/")[0]
        for pg in inv.get("pages", []):
            if pg.get("slug") == "home" and pg.get("cachedAt"):
                p = os.path.join(base, pg["cachedAt"])
                if os.path.isfile(p):
                    return p, host or os.path.basename(os.path.dirname(p))
    except (OSError, ValueError):
        pass
    cache = f"{base}/.reference/cache/_crawl"
    for pat in (f"{cache}/*/index.html", f"{cache}/*/*.html"):
        for cand in sorted(glob.glob(pat)):
            return cand, os.path.basename(os.path.dirname(cand))
    return None, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--home")
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--lang", default="",
                    help="source locale path prefix (fr-FR) to strip from slugs")
    ap.add_argument("--urls", action="store_true",
                    help="print the menu's internal hrefs (crawl list) and exit; "
                         "writes nothing")
    a = ap.parse_args()

    home, host = resolve_home(a.project, a.home)
    if not home:
        sys.exit(f"FAIL: no cached home page for {a.project} "
                 f"(page-inventory 'home' slug absent and no cached HTML found)")
    page = open(home, encoding="utf-8", errors="ignore").read()

    items = astro_nav(page)
    strategy = "astro-island navItems"
    if not items:
        items = dom_nav(page)
        strategy = "nav DOM"
    if not items:
        sys.exit("FAIL: no navigation structure found in the cached home page")

    if a.urls:
        # crawl-list mode: hrefs verbatim, menu order, nothing written
        for h in internal_hrefs(items, host):
            print(h)
        return

    lines, labels, externals = [], {}, []
    navmeta = {}   # leaf-slug -> mega-menu description (source navItems)

    def emit(nodes, parent_rel, depth):
        for it in nodes or []:
            if not isinstance(it, dict):
                continue
            label = (it.get("label") or "").strip()
            if not label:
                continue
            slug = internal_slug(it.get("href") or "#", host, a.lang)
            if slug is None and (it.get("href") or "#") not in ("#", "", "/"):
                externals.append((label, it.get("href")))
                continue  # external link: not a page — reported, never fabricated
            leaf = slug or slugify(label)   # pure section (href=#) -> slug of label
            rel = f"{parent_rel}/{leaf}" if parent_rel else leaf
            lines.append(rel)
            labels[leaf] = label
            desc = (it.get("description") or "").strip()
            if desc:
                navmeta[leaf] = desc
            if depth < a.max_depth and it.get("subMenu"):
                emit(it["subMenu"], rel, depth + 1)

    emit(items, "", 1)

    # multi-section IA (2026-07-23, scorecard ia[BUSINESS]/[ENTERPRISE] rendered
    # []): non-default sections live in the home page's section wrapper
    # (section-navs.json); their pages must NEST under the section root or the
    # section's L1 menu renders EMPTY (the nav is the page tree). A section
    # whose internal urls share ONE first segment nests under that root; the
    # prefixless default section is the emit() above.
    try:
        sn = json.load(open(f"projects/{a.project}/workflow-output/section-navs.json"))
    except Exception:
        sn = {}
    for sec_label, sec_items in (sn or {}).items():
        urls = []
        def _cu(its):
            for it in its or []:
                hh = (it.get("href") or "").split("#")[0].split("?")[0]
                if hh.startswith("/") and hh != "/":
                    urls.append(hh.strip("/"))
                _cu(it.get("subMenu"))
        _cu(sec_items)
        first = {u.split("/")[0] for u in urls}
        if len(first) != 1:
            continue
        root = first.pop()
        if root not in lines:
            lines.append(root)
            labels.setdefault(root, sec_label.title())
        emit(sec_items, root, 1)

    os.makedirs("orchestration/sitemaps", exist_ok=True)
    with open(f"orchestration/sitemaps/{a.project}.txt", "w") as f:
        f.write(f"# REAL site IA extracted from the source nav ({strategy})\n")
        f.write("\n".join(lines) + "\n")
    with open(f"orchestration/sitemaps/{a.project}.labels.json", "w") as f:
        json.dump(labels, f, indent=1, ensure_ascii=False)
    with open(f"orchestration/sitemaps/{a.project}.navmeta.json", "w") as f:
        json.dump(navmeta, f, indent=1, ensure_ascii=False)

    l1 = [x for x in lines if "/" not in x]
    print(f"[extract_nav] {strategy}: {len(lines)} menu path(s), "
          f"{len(l1)} L1 item(s): {', '.join(labels[x] for x in l1)}")
    if externals:
        print(f"[extract_nav] {len(externals)} external menu link(s) skipped "
              f"(not pages): " + "; ".join(f"{l} -> {h}" for l, h in externals[:6]))


if __name__ == "__main__":
    main()
