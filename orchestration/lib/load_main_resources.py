#!/usr/bin/env python3
"""load_main_resources.py — DETERMINISTIC jmix:mainResource loader (ETL phase 2.5).

Structured content (operator mandate 2026-07-21): entity units (news
articles, events, publications) are NOT pages and NOT frozen cardItems —
they are mainResource nodes created inside a jnt:contentFolder, listed by a
jcrQuery whose startNode targets the folder, rendered FULL PAGE at their own
URL, with the listing card linking via buildNodeUrl.

v2 (2026-07-21) — rewritten for the CURRENT pipeline. The v1 was
lesalondelaphoto-shaped (hardcoded origin, .reference/cache layout, old
content-load instance shapes). Post-hoc crawled entity pages have NO
segmentation artifacts ("signature 0 -> 0 promoted", observed live), so the
article core is read DIRECTLY from the localized mirror DOM — deterministic:
h1 -> jcr:title, first <time>/date pattern -> date, first content raster ->
DAM hero weakref, remaining <main> markup -> body (asset refs DAM-rewritten
through the SAME Loader machinery pages use).

EDIT-ONLY (Julian doctrine): no publication here — publish_site.py publishes
the declared folders right after /files (weakref targets must resolve in
LIVE before the listings that reference them).

Reads:
  orchestration/content/<p>.mainresource.json      (folders/type/prefixes)
  projects/<p>/workflow-output/page-inventory.json (slug ledger)
  projects/<p>/workflow-output/local-mirror/<slug>.html (article DOM)
Writes (via lib/load_content.Loader — the ONE sanctioned write+DAM path):
  /sites/<site>/contents/<folder>            (jnt:contentFolder, idempotent)
  one mainResource node per classified slug   (EDIT only)
  orchestration/content/<p>.mainresource-load.json (folder paths +
  listingPages -> folderPath, consumed by the listing wiring + gates)

Usage: load_main_resources.py <project> <site> [--locale en] [--dry]
"""
import argparse
import importlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup  # noqa: E402

_lc = importlib.import_module("load_content")

_RASTER = re.compile(r"\.(?:png|jpe?g|gif|webp|avif)(?:[?#]|$)", re.I)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}


def classified_slugs(project, cfg=None):
    """{slug: (folder_name, folder_cfg)} for every inventory slug under a
    declared entity prefix (and not itself a listing page). THE shared
    classification — extract_content / create_pages import this so entity
    details never enter the page tree."""
    if cfg is None:
        try:
            cfg = json.load(open(f"orchestration/content/{project}.mainresource.json"))
        except (OSError, ValueError):
            return {}
    try:
        inv = json.load(open(f"projects/{project}/workflow-output/page-inventory.json"))
    except (OSError, ValueError):
        return {}
    pgs = inv.get("pages") or inv
    slugs = set(pgs) if isinstance(pgs, dict) else {p.get("slug") for p in pgs if p.get("slug")}
    # SITEMAP slugs are PAGES, never entities: the source NAV links them, and
    # tree-driven menus render the page tree (observed: a KB article slug in
    # the Personal menu — deleting its page would hole the navigation)
    nav = set()
    try:
        for line in open(f"orchestration/sitemaps/{project}.txt"):
            sl = line.strip()
            if sl and not sl.startswith("#"):
                nav.add(sl.split("/")[-1].lower())
    except OSError:
        pass
    out = {}
    for fname, fcfg in (cfg.get("folders") or {}).items():
        listings = set(fcfg.get("listingPages") or [])
        for pref in fcfg.get("urlPrefixes") or []:
            sp = pref.strip("/").replace("/", "_") + "_"
            for s in slugs:
                if s.startswith(sp) and s not in listings and s.lower() not in nav:
                    out[s] = (fname, fcfg)
    return out


def entity_leaf(slug, fcfg):
    """Node name for a classified slug: the part after the MATCHING prefix
    (multi-prefix folders must test every prefix — using [0] named a node
    after the whole slug and broke the href rewire, observed live)."""
    for pr in fcfg.get("urlPrefixes") or []:
        sp = pr.strip("/").replace("/", "_") + "_"
        if slug.startswith(sp):
            return slug[len(sp):][:80]
    return slug[:80]


def parse_date(text):
    """First recognizable date in the text -> ISO (Jahia date prop)."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text or "")
    if m and m.group(2).lower() in _MONTHS:
        return (f"{m.group(3)}-{_MONTHS[m.group(2).lower()]:02d}-"
                f"{int(m.group(1)):02d}T00:00:00.000")
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text or "")
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}T00:00:00.000"
    return None


def article_core(mirror_path):
    """(title, date_iso, hero_file, body_html) from the localized article DOM.
    Deterministic: chrome stripped (header/footer/nav/aside/script), h1 is the
    title, the first raster in <main> is the hero (its single-image wrapper
    removed with it), the rest of <main> is the body markup."""
    soup = BeautifulSoup(open(mirror_path, encoding="utf-8", errors="replace").read(),
                         "lxml")
    main = soup.find("main") or soup.body
    # title BEFORE the chrome strip (support pages carry the h1 inside a
    # header element the strip removes — observed: empty jcr:title) and
    # require non-empty text (decorative empty h2 precedes real headings)
    title = ""
    for hel in main.find_all(["h1", "h2"]):
        title = re.sub(r"\s+", " ", hel.get_text(" ", strip=True)).strip()
        if title:
            break
    for el in main.find_all(["script", "style", "noscript", "template",
                             "header", "footer", "nav", "aside"]):
        el.extract()
    h1 = main.find(["h1", "h2"])
    date_iso = None
    t = main.find("time")
    if t is not None:
        date_iso = parse_date(t.get("datetime") or t.get_text(" ", strip=True))
    if not date_iso:
        date_iso = parse_date(main.get_text(" ", strip=True)[:1500])
    hero_file = None
    for img in main.find_all("img"):
        src = (img.get("src") or "").split("?")[0]
        if not _RASTER.search(src):
            continue
        hero_file = os.path.basename(src)
        unit = img
        p = unit.parent
        while getattr(p, "name", None) not in (None, "main", "body", "html") \
                and len(p.find_all("img")) == 1 and not p.get_text(strip=True):
            unit = p
            p = unit.parent
        unit.extract()
        break
    if h1 is not None:
        h1.extract()
    body = "".join(str(c) for c in main.children).strip()
    return title, date_iso, hero_file, body


def _exists(ld, path):
    try:
        r = ld.m.gql('query { jcr(workspace: EDIT) { nodeByPath(path: "%s") '
                     '{ path } } }' % path)
        return bool(((r or {}).get("jcr") or {}).get("nodeByPath"))
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("site")
    ap.add_argument("--locale", default="en")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(f"orchestration/content/{a.project}.mainresource.json"))
    slugs = classified_slugs(a.project, cfg)
    if not slugs:
        sys.exit("FAIL: load_main_resources — config declares folders but no "
                 "inventory slug classifies (crawl the detail pages first)")
    ld = _lc.Loader(a.project, a.site, locale=a.locale)
    contents = f"/sites/{a.site}/{cfg.get('contentsBase', 'contents')}"
    out = {"folders": {}, "listingPages": {}}
    created = updated = 0
    for fname, fcfg in (cfg.get("folders") or {}).items():
        fpath = f"{contents}/{fname}"
        if not a.dry and not _exists(ld, fpath):
            try:
                ld.m.create(contents, "jnt:contentFolder", {}, name=fname,
                            locale=a.locale)
                print(f"  + folder {fpath}")
            except Exception as e:
                sys.exit(f"FAIL: cannot create {fpath}: {str(e)[:140]}")
        out["folders"][fname] = {"path": fpath, "type": fcfg["type"]}
        for lp in fcfg.get("listingPages") or []:
            out["listingPages"][lp] = fpath
        for slug, (fn, _fc) in sorted(slugs.items()):
            if fn != fname:
                continue
            mp = f"projects/{a.project}/workflow-output/local-mirror/{slug}.html"
            if not os.path.isfile(mp):
                print(f"  ! mirror missing for {slug} — skipped", file=sys.stderr)
                continue
            title, date_iso, hero, body = article_core(mp)
            leaf = entity_leaf(slug, fcfg)
            npath = f"{fpath}/{leaf}"
            if a.dry:
                print(f"  [dry] {npath} <- {fcfg['type']} title={title[:48]!r} "
                      f"date={date_iso} hero={hero} body={len(body)}ch")
                continue
            if not _exists(ld, npath):
                try:
                    ld.m.create(fpath, fcfg["type"], {"jcr:title": title[:250]},
                                name=leaf, locale=a.locale)
                    created += 1
                    print(f"  + {npath}  ({title[:48]})")
                except Exception as e:
                    print(f"  ! create {leaf}: {str(e)[:140]}", file=sys.stderr)
                    continue
            post = {"body": ld._rewire_hrefs(body)[:200_000]}
            if date_iso:
                post["date"] = date_iso
            try:
                ld.m.update(npath, post, locale=a.locale)
                updated += 1
            except Exception as e:
                print(f"  ! props {leaf}: {str(e)[:140]}", file=sys.stderr)
            if hero:
                dam = ld.upload_dam(hero)
                if dam:
                    try:
                        ld.m.set_weakref(npath, "image", dam["path"], locale=a.locale)
                    except Exception as e:
                        print(f"  ! hero weakref {leaf}: {str(e)[:120]}",
                              file=sys.stderr)
    op = f"orchestration/content/{a.project}.mainresource-load.json"
    if not a.dry:
        json.dump(out, open(op, "w"), indent=1)
    print(f"load_main_resources: {created} created / {updated} wired over "
          f"{len(slugs)} classified slug(s) [EDIT-only] -> {op}")


if __name__ == "__main__":
    main()
