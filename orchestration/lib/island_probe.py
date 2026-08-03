#!/usr/bin/env python3
"""island_probe.py — deterministic INTERACTIVE-BEHAVIOUR census of the captured DOM.

A migration drops the source's JavaScript on purpose (it wipes the Jahia render,
scope rule `exclude-app-scripts`), so every behaviour the source shipped in JS
becomes a decision: **adopt it as a Jahia client island, or accept it as static.**
Made implicitly, that decision shows up as a frozen carousel with dead arrows
(operator finding 2026-07-21, singpost home) — the class this probe exists to
surface BEFORE the model is authored.

Deterministic: it reports the behaviour signatures present in the captured markup
and the DOM contract an island would have to honour. It decides nothing.

Signatures are matched on markup, not on a CMS: `data-properties` autoplay config,
vendor slider stems (swiffy-slider / swiper / slick / owl / glide / tiny-slider),
prev-next control pairs, collapsibles, tablists, facet/load-more listings, modals,
maps, embedded players, forms. Component boundaries come from the source's own
declaration when it has one (SXA `div.component`), else HTML sectioning.

Writes projects/<p>/workflow-output/island-inventory.json:
  {"units": [{"component", "behaviour", "instances", "pages", "contract": {...},
              "vendor", "shippedIsland"}], "byBehaviour": {...}}

Usage: island_probe.py <project>
"""
import json
import os
import re
import sys
from collections import defaultdict

from bs4 import BeautifulSoup

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# vendor slider/behaviour libraries, matched on class stems present in the markup
VENDORS = {
    "swiffy-slider": "swiffy-slider",
    "swiper": "swiper",
    "slick": "slick-slider",
    "owl-carousel": "owl-carousel",
    "glide": "glide.js",
    "tiny-slider": "tiny-slider",
    "flickity": "flickity",
    "splide": "splide",
    "embla": "embla",
}

# the islands the harness already ships (orchestration/templates/fidelity-shell/semantic)
SHIPPED = {
    "SourceCarousel": '[data-slot="carousel"]',
    "CarouselControls": None,   # semantic cardGrid carousel view, not captured markup
}

# SXA layout/state classes that are not a component identity (mirrors sxa-extract)
LAYOUT = re.compile(
    r"^(component-content|container|container-fluid|container-bp|row|col|col-\w+|"
    r"m[btxysep]?-\d+|p[btxysep]?-\d+|g[xy]?-\d+|gap-\d+|align-\w+|align-items-\w+|"
    r"justify-\w+|justify-content-\w+|d-\w+|d-md-\w+|d-lg-\w+|text-\w+|fs-\w+|fw-\w+|"
    r"w-\d+|h-\d+|mw-\d+|height0|parent-row|clearfix|initialized|active|show|first|"
    r"last|odd|even|rel-level\d|level\d|item\d+|submenu|bg-\w+|px-0|py-0)$")


def component_name(el):
    """The source's own name for this boundary, else its tag + first real class."""
    toks = [t for t in (el.get("class") or []) if t not in ("component", "component-content")]
    sem = [t for t in toks if not LAYOUT.match(t)]
    if sem:
        return sem[0]
    if el.get("data-component"):
        return str(el["data-component"])
    return el.name + (("." + toks[0]) if toks else "")


def boundaries(soup):
    """Component units: the source's declaration when it has one, else sectioning."""
    units = soup.select("div.component")
    if units:
        return units
    return soup.select("[data-component], section, main > div, article")


def sel(el):
    """A short, readable selector for one element (for the DOM contract)."""
    if el is None:
        return None
    cls = [c for c in (el.get("class") or []) if not LAYOUT.match(c)][:3]
    return el.name + ("." + ".".join(cls) if cls else "")


def detect(unit):
    """→ list of (behaviour, contract dict). A unit may carry more than one."""
    out = []
    cls_all = " ".join(unit.get("class") or [])
    inner_cls = " ".join(
        c for e in unit.find_all(True, limit=400) for c in (e.get("class") or []))
    hay = (cls_all + " " + inner_cls).lower()

    vendor = next((v for stem, v in VENDORS.items() if stem in hay), None)

    # ── sliding: a track of repeated items + (optionally) controls/indicators ──
    track = unit.select_one(
        'ul.slides, [data-slot="carousel-content"], ul.slider-container, '
        '.carousel-inner, .swiper-wrapper, .owl-stage, .glide__slides, .splide__list')
    items = unit.select('li.slide, [data-slot="carousel-item"], ul.slider-container > li, '
                        '.carousel-item, .swiper-slide, .owl-item, .splide__slide')
    props = unit.get("data-properties") or (
        unit.select_one("[data-properties]") or {}).get("data-properties") \
        if unit.select_one("[data-properties]") else unit.get("data-properties")
    autoplay = None
    if props:
        try:
            cfg = json.loads(props)
            autoplay = {k: cfg[k] for k in ("timeout", "isPauseEnabled", "transition")
                        if k in cfg} or None
        except (ValueError, TypeError):
            autoplay = {"raw": str(props)[:80]}
    if track is not None and len(items) >= 2:
        controls = [sel(b) for b in unit.select(
            'a.prev-text, a.next-text, button.slider-nav, .carousel-control-prev, '
            '.carousel-control-next, .swiper-button-prev, .swiper-button-next, '
            '.owl-prev, .owl-next')]
        indicators = unit.select(
            '.slider-indicators > button, .carousel-indicators > *, .swiper-pagination > *')
        out.append(("carousel", {
            "track": sel(track), "item": sel(items[0]), "items": len(items),
            "controls": [c for c in controls if c], "indicators": len(indicators),
            "autoplay": autoplay,
        }))

    # ── collapsibles / tabs ──
    if unit.select_one('[role="tablist"], .nav-tabs, [data-toggle="tab"], '
                       '[data-bs-toggle="tab"]'):
        panels = unit.select('[role="tabpanel"], .tab-pane')
        out.append(("tabs", {"tabs": len(unit.select('[role="tab"], .nav-tabs a, '
                                                     '.nav-tabs button')),
                             "panels": len(panels)}))
    coll = unit.select('[data-toggle="collapse"], [data-bs-toggle="collapse"], '
                       '[aria-expanded], details, .accordion-button')
    if coll and not unit.select_one('[role="tablist"]'):
        out.append(("collapsible", {"triggers": len(coll),
                                    "panels": len(unit.select('.collapse, .accordion-collapse, '
                                                              'details > *'))}))

    # ── listing behaviour that has NO Jahia backend (SXA search / facets) ──
    fac = [c for c in (unit.get("class") or []) if c.startswith("facet")]
    if fac or unit.select_one('[class*="facet"]'):
        out.append(("facetFilter", {"selects": len(unit.select("select")),
                                    "checkboxes": len(unit.select('input[type="checkbox"]')),
                                    "note": "SXA facets hit /sxa/search — no backend in Jahia"}))
    if unit.select_one('[class*="load-more"], .load-more, [data-loadmore]'):
        out.append(("loadMore", {"note": "paging driven by the source search API"}))

    # ── overlays, embeds, forms, maps ──
    if unit.select_one('.modal, [data-bs-toggle="modal"], [data-toggle="modal"], '
                       '[class*="popin"], [class*="lightbox"]'):
        out.append(("modal", {"triggers": len(unit.select(
            '[data-bs-toggle="modal"], [data-toggle="modal"], [class*="popin"]'))}))
    ifr = unit.select("iframe[src]")
    for f in ifr:
        src = f.get("src", "")
        if re.search(r"youtube|youtu\.be|vimeo|dailymotion", src, re.I):
            out.append(("videoPlayer", {"provider": re.sub(
                r"^.*?(youtube|youtu\.be|vimeo|dailymotion).*$", r"\1", src, flags=re.I)}))
        elif re.search(r"google\.com/maps|maps\.google|openstreetmap", src, re.I):
            out.append(("map", {"embed": "iframe"}))
    if unit.select_one('[class*="map-canvas"], #map, [data-map]') and not any(
            b == "map" for b, _ in out):
        out.append(("map", {"embed": "js-api"}))
    if unit.select_one("form"):
        f = unit.select_one("form")
        out.append(("form", {"action": (f.get("action") or "")[:60],
                             "inputs": len(unit.select("input, select, textarea")),
                             "note": "Sitecore ExperienceForms" if unit.select_one(
                                 '[class*="experience-form"], [data-sc-fieldid]') else ""}))
    if unit.select_one('video, source[type*="video"]') and not any(
            b == "videoPlayer" for b, _ in out):
        out.append(("videoPlayer", {"provider": "html5"}))

    return [(b, dict(c, vendor=vendor) if vendor else c) for b, c in out]


def main():
    proj = sys.argv[1]
    pp = f"{REPO}/projects/{proj}"
    inv = json.load(open(f"{pp}/workflow-output/page-inventory.json"))
    units = defaultdict(lambda: {"instances": 0, "pages": set(), "contract": None,
                                 "vendor": None})
    scripts = set()
    npages = 0
    for pg in inv.get("pages", []):
        cached = pg.get("cachedAt")
        path = os.path.join(pp, cached) if cached else None
        if not path or not os.path.exists(path):
            continue
        npages += 1
        soup = BeautifulSoup(open(path, encoding="utf-8", errors="replace").read(), "lxml")
        for s in soup.select("script[src]"):
            src = s["src"]
            for stem, v in VENDORS.items():
                if stem in src.lower():
                    scripts.add(v)
        for unit in boundaries(soup):
            name = component_name(unit)
            for behaviour, contract in detect(unit):
                e = units[(name, behaviour)]
                e["instances"] += 1
                e["pages"].add(pg["slug"])
                if e["contract"] is None:
                    e["contract"] = contract
                e["vendor"] = e["vendor"] or contract.get("vendor")

    rows = []
    for (name, behaviour), e in sorted(units.items(),
                                       key=lambda kv: (-kv[1]["instances"], kv[0])):
        shipped = None
        if behaviour == "carousel":
            c = e["contract"] or {}
            shipped = "SourceCarousel" if 'data-slot="carousel"' in json.dumps(c) else None
        rows.append({"component": name, "behaviour": behaviour,
                     "instances": e["instances"], "pages": sorted(e["pages"]),
                     "pageCount": len(e["pages"]),
                     "vendor": e["vendor"], "shippedIsland": shipped,
                     "contract": e["contract"]})
    by = defaultdict(int)
    for r in rows:
        by[r["behaviour"]] += r["instances"]
    out = {"project": proj, "pages": npages, "vendorScripts": sorted(scripts),
           "byBehaviour": dict(sorted(by.items(), key=lambda kv: -kv[1])), "units": rows}
    op = f"{pp}/workflow-output/island-inventory.json"
    json.dump(out, open(op, "w"), indent=1, ensure_ascii=False)
    print(f"island_probe: {npages} page(s), {len(rows)} behaviour-bearing unit(s) -> {op}")
    print(f"  by behaviour: {out['byBehaviour']}")
    for r in rows:
        v = f" [{r['vendor']}]" if r["vendor"] else ""
        s = f" (shipped: {r['shippedIsland']})" if r["shippedIsland"] else ""
        print(f"  {r['behaviour']:<13} {r['component']:<28} x{r['instances']:<3} "
              f"on {r['pageCount']} page(s){v}{s}")


if __name__ == "__main__":
    main()
