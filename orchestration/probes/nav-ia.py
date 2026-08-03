#!/usr/bin/env python3
"""nav-ia.py — IA gate: the extracted menu and the capture must agree.

The page tree IS the navigation (rule 13), so the sitemap extract_nav writes is
the site's information architecture. Two failure classes have each cost a run:

  1. **The extractor silently produced nothing.** nav_scope_crawl called
     `extract_nav --urls`, a flag that did not exist, so argparse exited 2, the
     stdout was empty, and the run reported "no extractable menu" on a site
     whose menu was right there in the captured DOM (salonphoto, 2026-08-03).
  2. **Slug identity drift.** On a locale-prefixed source the menu yields
     `fr-FR_salon` while the crawler (with --lang) captured `salon`, so every
     downstream join — pages, content-load, pixel gates — silently misses.

So this gate asserts the ARTIFACTS, not a threshold: a non-empty sitemap, no
locale-prefixed leaf, a label per leaf, and — once the menu-scoped crawl has
run — that every declared page was actually captured.

Usage: nav-ia.py <project> [--lang fr-FR]
"""
import argparse
import json
import re
import sys

LOCALEISH = re.compile(r"^[a-z]{2}([-_][A-Za-z]{2,4})?$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--lang", default="")
    a = ap.parse_args()
    p = a.project
    smap = f"orchestration/sitemaps/{p}.txt"
    lbl = f"orchestration/sitemaps/{p}.labels.json"
    fails, notes = [], []

    try:
        lines = [l.strip() for l in open(smap, encoding="utf-8")
                 if l.strip() and not l.startswith("#")]
    except OSError as e:
        sys.exit(f"FAIL nav-ia: no sitemap at {smap} ({e}) — extract_nav never "
                 f"produced the source IA")
    if not lines:
        fails.append(f"{smap} holds 0 menu paths")

    leaves = [l.split("/")[-1] for l in lines]
    l1 = [l for l in lines if "/" not in l]
    if not l1:
        fails.append("no L1 menu item (every path is nested — the menu root is lost)")

    prefixed = [s for s in leaves
                if (a.lang and s.split("_", 1)[0].lower() == a.lang.lower())
                or LOCALEISH.match(s.split("_", 1)[0])]
    if prefixed:
        hint = f"--lang {a.lang}" if a.lang else "--lang <locale>"
        fails.append(f"{len(prefixed)} sitemap leaf/leaves carry a locale prefix "
                     f"(e.g. {', '.join(prefixed[:3])}) — re-run extract_nav with {hint}")

    try:
        labels = json.load(open(lbl, encoding="utf-8"))
    except (OSError, ValueError):
        labels = {}
        fails.append(f"no labels at {lbl} — menu labels are the editor-visible IA")
    missing = [s for s in leaves if s not in labels]
    if labels and missing:
        fails.append(f"{len(missing)} leaf/leaves without a menu label "
                     f"(e.g. {', '.join(missing[:3])})")

    # capture agreement — only meaningful once the menu-scoped crawl has run
    try:
        inv = json.load(open(f"projects/{p}/workflow-output/page-inventory.json"))
        captured = {pg.get("slug") for pg in inv.get("pages", [])}
    except (OSError, ValueError):
        captured = set()
        notes.append("no page-inventory yet — capture agreement not checked")
    if captured:
        if len(captured) == 1 and len(lines) > 1:
            fails.append(f"sitemap declares {len(lines)} page(s) but the capture holds "
                         f"only {sorted(captured)} — the menu-scoped crawl never ran")
        else:
            # Precise expectation: nav-urls.txt is exactly what the crawler was ASKED
            # to fetch. Subtract the URLs the crawler deliberately skips as utility
            # (ticketing, newsletter, legal…) — those are a scope decision, not a
            # defect — and require every remaining one to have been captured.
            expected, utility = set(), []
            try:
                sys.path.insert(0, "orchestration/lib")
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "crawlsite", "orchestration/lib/crawl-site.py")
                cs = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cs)
                is_util = cs.is_utility_page
            except Exception:                                   # noqa: BLE001
                def is_util(_u):
                    return False
                notes.append("utility-pattern list unavailable — no scope subtraction")
            try:
                for line in open(f"projects/{p}/workflow-output/nav-urls.txt",
                                 encoding="utf-8"):
                    u = line.strip()
                    if not u:
                        continue
                    if is_util(u):
                        utility.append(u)
                        continue
                    segs = [s for s in u.split("/") if s]
                    if a.lang and segs and segs[0].lower() == a.lang.lower():
                        segs = segs[1:]
                    expected.add("_".join(segs) or "home")
            except OSError:
                notes.append("no nav-urls.txt — falling back to sitemap leaves")
                expected = {s for s in leaves if "_" in s}
            uncaptured = sorted(expected - captured)
            if uncaptured:
                fails.append(f"{len(uncaptured)} menu page(s) requested but not captured: "
                             f"{', '.join(uncaptured[:5])}")
            if utility:
                notes.append(f"{len(utility)} utility URL(s) out of scope by design "
                             f"({', '.join(u.split('/')[-1] for u in utility[:3])})")

    if fails:
        print(f"FAIL nav-ia [{p}]")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print(f"PASS nav-ia: {len(lines)} menu path(s), {len(l1)} L1, "
          f"{len(labels)} label(s), no locale drift"
          + (f" | {'; '.join(notes)}" if notes else ""))


if __name__ == "__main__":
    main()
