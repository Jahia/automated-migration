#!/usr/bin/env python3
"""Tests for orchestration/lib/zone_detect.py — the fine-signal-first zone/component detector.

Run: python3 orchestration/tests/test_zone_detect.py   (no pytest dependency)
Covers the units + the invariants that the adversarial verification pass established:
  - stem dehashing / utility filtering
  - identity tiers L0>L1>L2>L3
  - structural anchor gate (leaf style spans are not components)
  - ROOT-WRAPPER exclusion (the <body>/page-shell is never a zone)
  - site-chrome guard (ubiquitous editorial content is NOT chrome)
  - record detection (>=3 same-key siblings)
  - library_map deterministic mapping
  - smoke test on a real cached corpus page (if present)
"""
import os, sys, importlib.util

LIB = os.path.join(os.path.dirname(__file__), "..", "lib", "zone_detect.py")
spec = importlib.util.spec_from_file_location("zone_detect", LIB)
zd = importlib.util.module_from_spec(spec); spec.loader.exec_module(zd)
from bs4 import BeautifulSoup

_fails = []
def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + "  " + msg)
    if not cond:
        _fails.append(msg)

def ann(html):
    return zd.annotate(BeautifulSoup(html, "lxml").body, {})
def ann_df(html, df):
    return zd.annotate(BeautifulSoup(html, "lxml").body, df)

print("== stem dehashing / utility filter ==")
check(zd.stem("nav_item_arrow__JdbV0") == "nav_item_arrow", "CSS-module hash suffix stripped")
check(zd.stem("menu__link") == "menu__link", "BEM element (no upper/digit) NOT stripped")
check(zd.is_util("lg:col-span-8"), "Tailwind variant class is utility")
check(zd.is_util("col-12") and zd.is_util("d-flex") and zd.is_util("bg-white"), "Bootstrap utilities filtered")
check(zd.is_util("absolute") and zd.is_util("root") and zd.is_util("display-none"), "positional/plumbing filtered")
check(not zd.is_util("cmp-teaser") and not zd.is_util("asr-slide-item"), "semantic classes NOT utility")

print("== identity tiers (strongest wins) ==")
t = zd.identity("div", {"data-component": "basic_card", "class": ["x-y"], "role": "region"}, {})
check(t == ("cmp:basic_card", "L0"), f"L0 data-component wins over class/role (got {t})")
t = zd.identity("section", {"role": "banner"}, {})
check(t[1] == "L1" and t[0] == "role:banner", "L1 ARIA landmark")
t = zd.identity("footer", {}, {})
check(t == ("tag:footer", "L1"), "L1 semantic tag")
t = zd.identity("div", {"class": ["cmp-teaser", "col-6"]}, {})
check(t == ("cls:cmp-teaser", "L2"), f"L2 framework stem, utility ignored (got {t})")
t = zd.identity("div", {"class": ["asr-thing"]}, {"asr-thing": 5})
check(t == ("cls:asr-thing", "L3"), f"L3 recurring stem (docfreq>=3) (got {t})")
t = zd.identity("div", {"class": ["one-off"]}, {"one-off": 1})
check(t == (None, None), "non-recurring non-framework class is NOT an identity")
t = zd.identity("div", {"data-component": "button_0"}, {})
check(t[0] == "cmp:button", "data-component index suffix normalised (button_0 -> button)")

print("== full analyze on synthetic multi-page corpus ==")
# a 4-page site: shared header/footer chrome + a page-unique hero + a 3-card grid (records)
def page(uniq):
    cards = "".join(f'<div class="promo-card"><h3>Card {i}</h3><p>{uniq} body {i}</p></div>' for i in range(3))
    return f"""<html><body><div class="page-root">
      <header class="site-header"><nav class="main-nav"><a href="/">Home</a><a href="/x">Products</a><a href="/y">About</a></nav></header>
      <main>
        <section class="hero"><h1>{uniq} headline</h1><p>{uniq} intro copy that varies a lot per page</p></section>
        <div class="card-grid">{cards}</div>
        <p class="font-body">shared boilerplate line appearing on every page identically</p>
      </main>
      <footer class="site-footer"><a href="/tos">Terms</a><a href="/privacy">Privacy</a><a href="/cookies">Cookies</a></footer>
    </div></body></html>"""
import json, tempfile
class FakeInv:  # monkeypatch load() to feed synthetic pages
    pass
_pages = [(f"p{i}", BeautifulSoup(page(u), "lxml").body)
          for i, u in enumerate(["Alpha", "Bravo", "Charlie", "Delta"])]
_orig_load = zd.load
zd.load = lambda proj: _pages
try:
    R = zd.analyze("synthetic")
    agg = R["agg"]
    def scope_of(substr):
        for k, e in agg.items():
            if substr in k:
                return e["scope"], k
        return (None, None)
    # page-root wrapper must be ROOT, never a zone
    sc, k = scope_of("page-root")
    check(sc == "ROOT", f"page-root wrapper classified ROOT not a zone (got {sc} for {k})")
    # header/footer/nav: L1 semantic tag wins over class, so keys are tag:header/footer/nav
    check(agg.get("tag:footer", {}).get("scope") == "ABSOLUTE", "footer (tag:footer) is ABSOLUTE chrome")
    check(agg.get("tag:header", {}).get("scope") == "ABSOLUTE"
          or agg.get("tag:nav", {}).get("scope") == "ABSOLUTE", "header/nav is ABSOLUTE chrome")
    # the hero varies per page (different text) -> NOT chrome despite being on all pages
    sc, _ = scope_of("hero")
    check(sc != "ABSOLUTE", f"per-page-varying hero must NOT be chrome (got {sc})")
    # promo-card repeats 3x per parent -> RECORD
    sc, _ = scope_of("promo-card")
    check(sc == "RECORD", f"3 sibling cards -> RECORD (got {sc})")
    # font-body leaf text span is NOT an anchor/component
    check(not R["is_anchor"]("cls:font-body") if "cls:font-body" in agg else True,
          "leaf style span (font-body) is not a component anchor")
finally:
    zd.load = _orig_load

print("== library_map deterministic mapping ==")
cases = [("cls:asr-carousel-holder", "L3", "COMPONENT", 0, True, "carousel"),
         ("cls:promo-card", "L3", "RECORD", 3, False, "card"),
         ("cmp:accordion", "L0", "COMPONENT", 0, True, "accordion"),
         ("cls:brands-logo", "L2", "COMPONENT", 0, True, "logoWall"),
         ("cls:main-heading", "L3", "COMPONENT", 0, False, "heading"),
         ("cls:asr-section-rich-text", "L3", "COMPONENT", 0, False, "richText")]
for key, tier, scope, sib, kids, expect in cases:
    got, conf = zd.library_map(key, tier, scope, sib, kids)
    check(got == expect, f"library_map({key}) -> {got} (expected {expect}, conf {conf})")

# anti-overfit regression: the bare "grid" token must NOT map to cardGrid — it matched
# layout frameworks (aem-Grid, responsivegrid, Bootstrap main-grid) and typed layout
# wrappers as cardGrids. Only card-INTENT words map; genuine card grids are reached via
# the selective-parent is_card_grid gate. (Do not reintroduce "grid" here.)
for layout_key in ("cls:main-grid", "cls:aem-Grid", "cls:responsivegrid", "cls:asr-grid-layouts"):
    got, conf = zd.library_map(layout_key, "L3", "COMPONENT", 3, True)
    check(got != "cardGrid" or conf < 0.5,
          f"layout grid {layout_key} is NOT a confident cardGrid (got {got}@{conf})")
for card_key in ("cls:card-grid", "cls:product-cards", "cls:cards-list"):
    got, conf = zd.library_map(card_key, "L3", "COMPONENT", 3, True)
    check(got == "cardGrid", f"card-intent {card_key} still maps to cardGrid (got {got})")

print("== smoke test on a real cached page (if present) ==")
REPO = os.path.join(os.path.dirname(__file__), "..", "..")
import glob
real = glob.glob(os.path.join(REPO, "projects", "contentful", ".reference", "cache", "_crawl", "**", "*.html"), recursive=True)
if real:
    body = BeautifulSoup(open(real[0], encoding="utf-8", errors="replace").read(), "lxml").body
    df = zd.stem_docfreq([body])
    a = zd.annotate(body, df)
    keys = [n["key"] for n in zd.walk(a) if n["key"]]
    check(len(keys) > 20, f"real page yields many identities ({len(keys)})")
    check(any(k.startswith("cmp:") for k in keys), "real contentful page has data-component (L0) identities")
else:
    print("  skip  (no cached corpus on disk)")

print()
if _fails:
    print(f"FAILED {len(_fails)} check(s):")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("ALL TESTS PASSED")
