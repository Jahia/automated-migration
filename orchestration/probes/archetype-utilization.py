#!/usr/bin/env python3
"""archetype-utilization — the model's types must actually be USED.

2026-07-23 finding (operator): the zone map identified components well, yet the
site loaded as THREE types — a needs_mr misroute sent 120/243 anatomy roles to
the article type, 9 of 11 model types carried ZERO instances, and no gate
noticed because pixel fidelity rides the skeletons, not the types. The model
was approved with 11 types; the pipeline delivered 3.

Checks (against the ARTIFACT — component-manifest.json instanceTypeMap +
per-component frequency; no proxy):
  1. concentration: no single content type claims > 40% of mapped roles
  2. utilization:  >= 5 distinct content types carry frequency > 0
  3. entity leak:  the mainResource entity type claims <= 10% of roles
     (entities live in contentFolders; page bands are page components)

Chrome (siteHeader/footer/mainNavigation), structural tools (rawHtml/
subNavigation/jcrQuery/cols) and child types never count toward concentration.

Usage: archetype-utilization.py <project> [--manifest PATH]
"""
import argparse
import json
import sys
from collections import Counter

STRUCTURAL = {"rawHtml", "subNavigation", "jcrQuery", "cols", "gridRow",
              "breadcrumb", "siteHeader", "footer", "mainNavigation",
              "cardItem", "cta"}
MAX_SHARE = 0.40
MIN_LIVE_TYPES = 5
MAX_ENTITY_SHARE = 0.10


def local(nt):
    return nt.split(":", 1)[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--manifest")
    a = ap.parse_args()
    mp = a.manifest or f"projects/{a.project}/workflow-output/component-manifest.json"
    m = json.load(open(mp))
    itm = m.get("instanceTypeMap") or {}
    comps = m.get("components") or []

    content_roles = Counter(nt for nt in itm.values()
                            if local(nt) not in STRUCTURAL)
    total = sum(content_roles.values())
    bad = []
    if not total:
        bad.append("gate-blind: instanceTypeMap holds no content-type roles")
    else:
        for nt, c in content_roles.most_common():
            share = c / total
            if share > MAX_SHARE:
                bad.append(f"concentration: {nt} claims {c}/{total} roles "
                           f"({share:.0%} > {MAX_SHARE:.0%}) — the classifier is "
                           f"collapsing the anatomy universe onto one type")
        # entity leak — mainResource types must stay rare on PAGE roles
        mr_types = {c["nodeType"] for c in comps
                    if c.get("needsMainResource")
                    or "jmix:mainResource" in (c.get("supertypes") or [])
                    or "jmix:mainResource" in (c.get("mixins") or [])}
        for nt in mr_types:
            c = content_roles.get(nt, 0)
            if c / total > MAX_ENTITY_SHARE:
                bad.append(f"entity-leak: mainResource type {nt} claims {c}/{total} "
                           f"page roles ({c / total:.0%} > {MAX_ENTITY_SHARE:.0%}) — "
                           f"page bands must never route to the entity type")
    live = [c["nodeType"] for c in comps
            if (c.get("frequency") or 0) > 0 and local(c["nodeType"]) not in STRUCTURAL]
    if len(live) < MIN_LIVE_TYPES:
        bad.append(f"utilization: only {len(live)} content type(s) carry instances "
                   f"({', '.join(live) or 'none'}) < {MIN_LIVE_TYPES} — the model's "
                   f"types are dead weight")

    # LOADED distribution (2026-07-23, second blind spot): role shares can be
    # healthy while the PAYLOAD skews — generic high-frequency wrapper roles
    # ('relative', 'w-full') are first-claimed by one archetype's regions, so
    # occurrence-weighted typing collapses again (hero took 65% of loaded
    # bands while the role shares read fine). Measure the artifact that
    # actually loads: top-level instances per resolved type.
    try:
        cl = json.load(open(f"orchestration/content/{a.project}.content-load.json"))
        litm = {k.lower(): v for k, v in itm.items()}
        loaded = Counter()
        for pg in (cl.get("pages") or {}).values():
            for i in pg.get("instances") or []:
                nt = i.get("nodeType") or litm.get((i.get("type") or "").lower())
                if nt and local(nt) not in STRUCTURAL:
                    loaded[nt] += 1
        ltotal = sum(loaded.values())
        # A PAYLOAD THAT LOADS NOTHING IS THE WORST STATE, NOT THE BEST (2026-08-04).
        # The concentration test below is share-based, so an EMPTY payload divides by
        # nothing, adds no finding, and this gate reported PASS with its healthy-looking
        # manifest role shares — measured live: semanticize emptied all 27 pages
        # (556 instances in, 0 out) and this printed "PASS ... 6 live type(s)". A gate
        # that cannot measure must fail. The file's ABSENCE is still fine (pre-extract),
        # but its presence is a promise that content was produced.
        if ltotal == 0:
            bad.append("the content-load exists but carries ZERO typed instances — "
                       "extraction or semanticize emptied the payload; nothing would "
                       "load and every share-based check below is vacuous")
        empty_pages = sorted(sl for sl, pg in (cl.get("pages") or {}).items()
                             if not (pg.get("instances") or []))
        if empty_pages and len(empty_pages) == len(cl.get("pages") or {}):
            bad.append(f"all {len(empty_pages)} page(s) in the payload have zero "
                       f"instances")
        elif empty_pages:
            bad.append(f"{len(empty_pages)} page(s) carry zero instances: "
                       + ", ".join(empty_pages[:6]))
        for nt, c in loaded.most_common():
            if ltotal and c / ltotal > 0.50:
                bad.append(f"loaded-concentration: {nt} carries {c}/{ltotal} loaded "
                           f"bands ({c / ltotal:.0%} > 50%) — the role->type bridge "
                           f"is occurrence-collapsing (generic wrapper roles "
                           f"first-claimed by one archetype)")
    except (FileNotFoundError, ValueError):
        pass   # pre-extract phases: manifest checks above still gate

    if bad:
        print("FAIL: archetype-utilization —", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        sys.exit(1)
    dist = ", ".join(f"{local(nt)}={c}" for nt, c in content_roles.most_common(8))
    print(f"PASS: archetype-utilization — {len(live)} live type(s), "
          f"role shares: {dist}")


if __name__ == "__main__":
    main()
