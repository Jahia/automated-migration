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
