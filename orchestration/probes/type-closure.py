#!/usr/bin/env python3
"""type-closure.py — every node type the LOAD will ask for must exist in the CND.

The load payload and the CND are produced by different steps from different
inputs (extract_content/semanticize_content vs cnd_emit), and nothing checked
that the set of types the first asks for is contained in the set the second
declares. When it is not, the load does not fail loudly: it creates what it can
and throws ConstraintViolationException on the rest, leaving a site that looks
populated with holes in it — the kind of result that reads as "mostly worked".

Measured on salonphoto before this gate existed, 57 instances referenced types
no CND declared:
  * sdp:accordionItem (34) — the accordion's OWN childType, in the manifest,
    simply never emitted by cnd_emit;
  * rawHtml (16) — the passthrough type written without its namespace, while
    the CND declares sdp:rawHtml;
  * sdp:cardGridItem (7) — a second name for the card item the CND calls
    sdp:cardItem.

Three different producers, one invariant. Set containment is exactly checkable,
needs no threshold, and cannot be satisfied by anything except the two artifacts
agreeing.

FAILS when a type referenced by the content-load payload (or the entity map) is
absent from the CND, and when the CND is missing/unreadable while a payload
exists (a gate that cannot measure must fail).

Usage: type-closure.py <project> [--cnd PATH] [--load PATH]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter


def walk_types(x, out):
    """Every string under a `nodeType` key, at any depth.

    `nodeType` ONLY, deliberately. A first version also collected `type`, which in
    this payload names the SOURCE ROLE a region came from — `content`, `rich-text`,
    `title`, `carousel-atom`, `page-list` — and reported 23 "missing types" of which
    20 were roles that were never meant to be node types. A gate that reports
    nonsense alongside real findings gets ignored wholesale, so it has to name only
    what the loader will actually pass to a create call."""
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "nodeType" and isinstance(v, str) and v.strip():
                out[v.strip()] += 1
            else:
                walk_types(v, out)
    elif isinstance(x, list):
        for v in x:
            walk_types(v, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--cnd", default="")
    ap.add_argument("--load", default="")
    a = ap.parse_args()
    p = a.project
    wo = f"projects/{p}/workflow-output"
    cnd_p = a.cnd or f"{wo}/definitions.cnd"
    load_p = a.load or f"orchestration/content/{p}.content-load.json"

    if not os.path.exists(load_p):
        print(f"PASS type-closure: no load payload at {load_p} — nothing to check")
        return
    if not os.path.exists(cnd_p):
        sys.exit(f"FAIL type-closure: {load_p} exists but {cnd_p} does not — the load "
                 f"would ask a repository for types nothing has declared")

    cnd = open(cnd_p, encoding="utf-8", errors="replace").read()
    declared = set(re.findall(r"^\[([\w:]+)\]", cnd, re.M))
    if not declared:
        sys.exit(f"FAIL type-closure: {cnd_p} declares no node type at all")

    refs = Counter()
    walk_types(json.load(open(load_p)), refs)
    # the entity map names the types load_main_resources will create
    mrp = f"orchestration/content/{p}.mainresource.json"
    if os.path.exists(mrp):
        for f in (json.load(open(mrp)).get("folders") or {}).values():
            if f.get("type"):
                refs[f["type"]] += 1

    # jnt:/jmix:/nt:/mix: are platform types, not ours to declare
    PLATFORM = re.compile(r"^(jnt|jmix|nt|mix|jcr|jahiant|jahiamix):")
    missing = {t: n for t, n in refs.items()
               if t not in declared and not PLATFORM.match(t)}
    if missing:
        print(f"FAIL type-closure [{p}] — {len(missing)} type(s) the load asks for are "
              f"not in {os.path.basename(cnd_p)}")
        for t, n in sorted(missing.items(), key=lambda kv: -kv[1]):
            hint = ""
            if ":" not in t:
                hint = " (no namespace — the payload writer dropped the prefix)"
            else:
                near = [d for d in declared
                        if d.split(":")[-1].lower().startswith(t.split(":")[-1][:6].lower())]
                if near:
                    hint = f" (CND has {', '.join(sorted(near)[:2])})"
            print(f"  - {t}: {n} instance(s){hint}")
        print("  Fix: emit the type in cnd_emit, or write the declared name in the "
              "payload. Unfixed, the load creates what it can and throws "
              "ConstraintViolationException on the rest — a site with holes.")
        sys.exit(1)

    ours = {t: n for t, n in refs.items() if not PLATFORM.match(t)}
    print(f"PASS type-closure: {len(ours)} project type(s), "
          f"{sum(ours.values())} instance(s), all declared in "
          f"{os.path.basename(cnd_p)} ({len(declared)} types)")


if __name__ == "__main__":
    main()
