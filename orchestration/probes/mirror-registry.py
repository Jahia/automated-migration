#!/usr/bin/env python3
"""mirror-registry.py — the mirror's ASSET REGISTRY must be at least as rich as
its pages need (producer: localize_site.py).

step_localize's only registry gate was `test -s mirror.json`, which asks whether
the file has bytes. A mirror.json with `"urlMap": {}` and
`"assets": {"total": 0}` has plenty of bytes, so the gate stayed green on a
mirror that serves nothing — while 1063 asset files and every page's
`assets/<hash>.<ext>` reference sat intact on disk (2026-08-04, self-inflicted:
an incremental localize seeded its carry-forward map from a mirror.json a killed
run had left without one, then "reused" all 169 pages and wrote the empty
registry back). Downstream, offline rendering serves the pages and every image,
stylesheet and font resolves to nothing — a mirror that LOOKS complete. The
pixel and self-containment gates run against that mirror, so the whole fidelity
story would have been measured on an assetless render.

The registry is therefore checked against what the mirror actually references:

  1. pages reference assets but the urlMap is EMPTY -> the registry was lost,
  2. a referenced asset file is MISSING from assets/ -> dangling reference,
  3. the urlMap covers < --min-cover of the distinct referenced files -> a
     partial registry (a rebuild that died midway writes one).

Reference-derived, so it cannot be satisfied by a threshold: a mirror that
references nothing passes trivially, and one that references 1063 files must
have them.

Usage: mirror-registry.py <project> [--min-cover 0.95]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

REF = re.compile(r"""assets/([0-9A-Za-z_.-]+\.[0-9A-Za-z]{1,6})""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--min-cover", type=float, default=0.95)
    a = ap.parse_args()
    proj = a.project if a.project.startswith("projects/") else f"projects/{a.project}"
    mdir = f"{proj}/workflow-output/local-mirror"
    mjson = f"{mdir}/mirror.json"
    if not os.path.isdir(mdir):
        sys.exit(f"FAIL mirror-registry: no mirror at {mdir}")
    try:
        m = json.load(open(mjson))
    except (OSError, ValueError) as e:
        sys.exit(f"FAIL mirror-registry: cannot read {mjson} ({e})")

    urlmap = m.get("urlMap") or {}
    # the registry maps source URL -> local path; collect the local file names it knows
    known = set()
    for v in urlmap.values():
        v = v if isinstance(v, str) else (v or {}).get("local", "")
        known.add(os.path.basename(str(v)))
    known.discard("")

    pages = sorted(f for f in os.listdir(mdir) if f.endswith(".html"))
    refs = Counter()
    for fn in pages:
        try:
            html = open(os.path.join(mdir, fn), encoding="utf-8",
                        errors="replace").read()
        except OSError:
            continue
        for name in REF.findall(html):
            refs[name] += 1

    on_disk = set()
    adir = os.path.join(mdir, "assets")
    if os.path.isdir(adir):
        on_disk = set(os.listdir(adir))

    fails = []
    distinct = set(refs)
    if distinct and not urlmap:
        fails.append(
            f"{len(pages)} page(s) reference {len(distinct)} distinct asset file(s) "
            f"but mirror.json's urlMap is EMPTY — the registry was lost; the mirror "
            f"renders with no images, CSS or fonts. Re-run localize_site.py --force")

    missing = sorted(distinct - on_disk)
    if missing:
        fails.append(f"{len(missing)} referenced asset file(s) are MISSING from "
                     f"assets/ (e.g. {', '.join(missing[:4])}) — dangling reference(s)")

    if distinct and urlmap:
        cover = len(distinct & known) / len(distinct)
        if cover < a.min_cover:
            fails.append(f"urlMap covers only {cover:.1%} of the {len(distinct)} "
                         f"referenced asset file(s) (< {a.min_cover:.0%}) — partial "
                         f"registry, likely a rebuild that did not finish")

    rec = m.get("assets") or {}
    if distinct and not (rec.get("total") or 0):
        fails.append(f"mirror.json records assets.total=0 while its pages reference "
                     f"{len(distinct)} file(s) — the record contradicts the mirror")

    if fails:
        print(f"FAIL mirror-registry [{mjson}]")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print(f"PASS mirror-registry: {len(pages)} page(s) reference {len(distinct)} "
          f"asset file(s), all present on disk, urlMap {len(urlmap)} entr"
          f"{'y' if len(urlmap) == 1 else 'ies'}")


if __name__ == "__main__":
    main()
