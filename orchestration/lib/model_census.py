#!/usr/bin/env python3
"""model_census.py — deterministic corpus census feeding the MODEL phase
(MIGRATION-V3 Phase 1). Summarizes the mirror so the model author (Claude,
operator-reviewed) judges from evidence, never from thresholds:

  * top-level BAND families by anatomy signature (grid / carousel /
    collapsible / table / aside / repeat / plain) with a sample each
  * ENTITY candidates: uncrawled internal link targets clustered by prefix
    + crawled leaf clusters reached from cards
  * CTA anatomies (button-ish vs text-arrow vs icon)
  * chrome regions present

BAND BOUNDARY (2026-08-03): a band was `main.find_all("section")`, which is a
markup dialect, not a universal. Sitecore SXA declares every band as
`div.component <type>` and emits ZERO <section> elements, so on salonphoto the
census reported **0 families for a 17-component page** — the evidence artifact
the model author reads was empty, silently. The boundary is now, in order:
the source's OWN declaration (`div.component` / `[data-component]`, top-level
only), then `<section>`, then `main`'s top-level children; the mode used is
reported as `boundary` so the artifact says how it measured. `probes/
census-coverage.py` fails when any captured page yields no band.

Writes projects/<p>/workflow-output/model-census.json and prints the digest.
Usage: model_census.py <project>
"""
import json
import os
import re
import sys
from collections import Counter

from bs4 import BeautifulSoup


DECLARED = "div.component, [data-component], [data-testid]"
LAYOUTISH = re.compile(
    r"^(component-content|container|container-fluid|container-bp|row|col|col-\w+|"
    r"m[btxysep]?-\d+|p[btxysep]?-\d+|g[xy]?-\d+|d-\w+|text-\w+|w-\d+|h-\d+|bg-\w+|"
    r"height0|px-0|py-0|clearfix|active|show|first|last|odd|even)$")


def band_name(el):
    """The source's own name for a band, else its tag."""
    if el.get("data-component"):
        return str(el["data-component"])
    toks = [t for t in (el.get("class") or [])
            if t not in ("component", "component-content") and not LAYOUTISH.match(t)]
    return toks[0] if toks else el.name


def _vis_len(el):
    return len(re.sub(r"\s+", " ", el.get_text(" ", strip=True)))


def _declared_roots(el):
    return [d for d in el.select(DECLARED)
            if not any(a is not el and (
                "component" in (a.get("class") or []) or a.get("data-component"))
                for a in d.parents)]


def bands(main_el, _depth=0):
    """(units, mode) — top-level content bands under the main region.

    COVERAGE, not presence — for EVERY tier (2026-08-04). The first version of this
    fix measured coverage only for the source's declaration and still took `<section>`
    merely because sections EXISTED. On a Sitecore *item* template that is the same
    bug one tier down: a programme event's two `<section>`s hold the date strip and
    the TAB LABELS ("Sessions Description Thematiques"), 254 of the region's 2595
    chars, while the top-level wrapper holds all 2595. Every event therefore loaded a
    227-char body of tab labels and no prose — and entity-payload passed it, because
    a body of labels clears a `>= 40 chars` floor. Presence tests keep failing the
    same way: they answer "is there a boundary?" when the question is "does this
    boundary account for the content?"

    So: score all tiers, take the first that covers at least half the region, and if
    the winner is a lone wrapper holding essentially everything, DESCEND into it —
    one 2595-char band is the flat richtext the entity doctrine exists to prevent."""
    total = _vis_len(main_el)
    dec = _declared_roots(main_el)
    secs = [s for s in main_el.find_all("section") if not s.find_parent("section")]
    tl = [c for c in main_el.find_all(["div", "article", "section", "ul", "ol"],
                                      recursive=False) if _vis_len(c) or c.find("img")]
    # order matters: the source's own declaration wins when it accounts for the text
    tiers = [("declared", dec), ("section", secs), ("toplevel-div", tl)]

    for name, units in tiers:
        if not units:
            continue
        covered = sum(_vis_len(u) for u in units)
        if not (total == 0 or covered / total >= 0.5):
            continue
        # a single unit covering the whole region is a WRAPPER, not a band list.
        # The chain is as deep as the source's markup: on a programme event it runs
        # main > .container > .row > .external-content-wrapper > .VueWrapper >
        # .container-events > .container before reaching 6 real bands, so a depth-4
        # cap returned the wrapper and the body stayed one flat blob. Descend as far
        # as the wrappers go (8 is well past any observed chain, and each level must
        # still be a LONE child covering >90%, so it cannot walk into content).
        if len(units) == 1 and _depth < 8 and total and covered / total > 0.9:
            inner, imode = bands(units[0], _depth + 1)
            if len(inner) > 1:
                return inner, f"{name}>{imode}"
        return units, name

    if dec:
        # mixed: declared roots AND the uncovered item-template siblings — the page
        # mixes an SXA component with item markup and dropping either loses content
        covered = sum(_vis_len(d) for d in dec)
        mixed = dec + [s for s in tl if s not in dec
                       and not any(d in s.descendants for d in dec)
                       and _vis_len(s) > 0]
        if mixed and sum(_vis_len(x) for x in mixed) > covered:
            return mixed, f"declared+item ({covered}/{total} chars declared)"
    for name, units in tiers:
        if units:
            return units, f"{name} (under-covering)"
    return [], "empty"


def repeats(el):
    """max count of same-signature sibling children (the generic RECORD signal)."""
    best = 0
    for parent in [el] + el.find_all(True, limit=200):
        sig = Counter()
        for k in parent.find_all(True, recursive=False):
            cls = " ".join(c for c in (k.get("class") or []) if not LAYOUTISH.match(c))
            sig[(k.name, cls)] += 1
        if sig:
            best = max(best, max(sig.values()))
    return best


def main():
    p = sys.argv[1]
    mirror = f"projects/{p}/workflow-output/local-mirror"
    inv = {}
    try:
        _i = json.load(open(f"projects/{p}/workflow-output/page-inventory.json"))
        pgs = _i.get("pages") or _i
        inv = set(pgs) if isinstance(pgs, dict) else {x.get("slug") for x in pgs}
    except (OSError, ValueError):
        inv = set()
    fams, samples = Counter(), {}
    types, type_sig = Counter(), {}
    modes, per_page = Counter(), {}
    cta_anat = Counter()
    uncrawled = Counter()
    files = sorted(f for f in os.listdir(mirror) if f.endswith(".html"))
    for fn in files:
        soup = BeautifulSoup(open(os.path.join(mirror, fn), encoding="utf-8",
                                  errors="replace").read(), "lxml")
        main_el = soup.find("main") or soup.body
        if main_el is None:
            continue
        units, mode = bands(main_el)
        modes[mode] += 1
        per_page[fn[:-5]] = len(units)
        for sec in units:
            parts = []
            if sec.select_one('[data-slot="carousel"], [class*="swiper"], [class*="slider"], '
                              '[class*="carousel"], ul.slides, [class*="owl-"], '
                              '[class*="splide"], [class*="glide"]'):
                parts.append("carousel")
            if sec.select_one('[data-state], [data-slot="collapsible"], details, '
                              '[data-toggle="collapse"], [data-bs-toggle="collapse"], '
                              '[class*="accordion"], [role="tablist"], [class*="nav-tabs"]'):
                parts.append("collapsible")
            if sec.select_one('[class*="grid-cols"], [class*="grid "], [class*=" grid"], '
                              '[class*="-grid"]'):
                parts.append("grid")
            if sec.find("aside") or sec.find_parent("aside"):
                parts.append("aside")
            if sec.find("table"):
                parts.append("table")
            if repeats(sec) >= 3 and "grid" not in parts and "carousel" not in parts:
                parts.append("repeat")
            sig = "+".join(parts) or "plain"
            fams[sig] += 1
            name = band_name(sec)
            types[name] += 1
            type_sig.setdefault(name, sig)
            if sig not in samples:
                h = sec.find(["h1", "h2", "h3"])
                samples[sig] = {"page": fn[:-5], "band": name,
                                "heading": (h.get_text(strip=True)[:60] if h else ""),
                                "imgs": len(sec.find_all("img")),
                                "links": len(sec.find_all("a"))}
        for a in main_el.find_all("a", href=True):
            h = a["href"].split("#")[0].split("?")[0]
            cls = " ".join(a.get("class") or []).lower()
            if re.search(r"btn|button|bg-", cls):
                cta_anat["button"] += 1
            elif a.find("svg") and not a.get_text(strip=True):
                cta_anat["iconLink"] += 1
            elif a.find("svg"):
                cta_anat["textArrow"] += 1
            if h.startswith("/") and h != "/":
                slug = h.strip("/").replace("/", "_")
                if inv and slug not in inv \
                        and not re.search(r"\.(pdf|jpe?g|png|zip|docx?)$", h, re.I):
                    uncrawled["/".join(h.strip("/").split("/")[:-1]) or "(root)"] += 1
    out = {
        "pages": len(files),
        "boundary": dict(modes),
        "bandsPerPage": per_page,
        "sectionFamilies": [{"signature": k, "count": v, "sample": samples.get(k)}
                            for k, v in fams.most_common()],
        "bandTypes": [{"band": k, "count": v, "signature": type_sig.get(k)}
                      for k, v in types.most_common()],
        "ctaAnatomies": dict(cta_anat),
        "uncrawledPrefixes": [{"prefix": k, "links": v}
                              for k, v in uncrawled.most_common(15)],
        "chrome": {"header": True, "footer": True},
    }
    op = f"projects/{p}/workflow-output/model-census.json"
    json.dump(out, open(op, "w"), indent=1)
    print(f"model_census: {len(files)} page(s), "
          f"{len(fams)} section famil{'y' if len(fams) == 1 else 'ies'} -> {op}")
    for row in out["sectionFamilies"][:10]:
        s = row["sample"] or {}
        print(f"  {row['signature']}: x{row['count']}  "
              f"e.g. {s.get('page', '')[:36]} '{s.get('heading', '')[:36]}'")


if __name__ == "__main__":
    main()
