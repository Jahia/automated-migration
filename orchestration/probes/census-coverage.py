#!/usr/bin/env python3
"""census-coverage.py — the model-phase EVIDENCE gate.

`step_model_census` asserted only `test -s model-census.json`, so a census that
parsed every page and saw NOTHING passed: on salonphoto (Sitecore SXA) the band
unit was `<section>`, the source emits none, and the artifact came out with 0
families for a 17-component page. The model author would then have judged the
component model from an empty file — the exact "producer that cannot measure"
class the doctrine forbids.

FAILS when:
  1. the census is missing / unparseable / reports 0 pages,
  2. any censused page contributed 0 bands (a page the census cannot see),
  3. a mirror page is absent from the census (silently skipped),
  4. no band family was found at all.

Usage: census-coverage.py <project>
"""
import json
import os
import sys


def main():
    p = sys.argv[1]
    pp = f"projects/{p}"
    cpath = f"{pp}/workflow-output/model-census.json"
    try:
        c = json.load(open(cpath))
    except (OSError, ValueError) as e:
        sys.exit(f"FAIL census-coverage: cannot read {cpath} ({e})")

    fails = []
    if not c.get("pages"):
        fails.append("census reports 0 pages")
    per = c.get("bandsPerPage") or {}
    if not per:
        fails.append("no bandsPerPage ledger — census predates the boundary fix, re-run it")
    blind = sorted(k for k, v in per.items() if not v)
    if blind:
        fails.append(f"{len(blind)} page(s) yielded 0 content bands: "
                     f"{', '.join(blind[:6])} — the band boundary does not fit this source")
    if not c.get("sectionFamilies"):
        fails.append("0 band families — the census saw no content anywhere")

    mirror = f"{pp}/workflow-output/local-mirror"
    if os.path.isdir(mirror):
        pages = {f[:-5] for f in os.listdir(mirror) if f.endswith(".html")}
        missed = sorted(pages - set(per))
        if missed:
            fails.append(f"{len(missed)} mirrored page(s) never censused: "
                         f"{', '.join(missed[:6])}")

    if fails:
        print(f"FAIL census-coverage [{p}]")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    total = sum(per.values())
    print(f"PASS census-coverage: {c['pages']} page(s), {total} band(s), "
          f"{len(c['sectionFamilies'])} famil(y/ies), boundary={c.get('boundary')}, "
          f"min {min(per.values())} band(s)/page")


if __name__ == "__main__":
    main()
