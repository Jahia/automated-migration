#!/usr/bin/env python3
"""zone-source.py — identification must read the SCOPED bytes.

scope_apply.py turns local-mirror/ into the scoped reference (exclusions applied,
decided once, recorded in scope-rules.json). Every downstream consumer reads it.
zone_detect used to read the RAW crawl cache instead, so declared exclusions had
no effect on identification: on salonphoto the OneTrust consent SDK (27/27 pages)
supplied 20+ of the 35 ABSOLUTE keys and would have been modelled as site chrome.

FAILS when scope-rules.json declares at least one rule but the emitted zone model
was built from anything other than the scoped mirror — i.e. you cannot claim a
zoning map while identifying components from bytes you already declared out of
scope. Also fails on a missing/unstamped model (a model that cannot say what it
read cannot be trusted).

Usage: zone-source.py <project>
"""
import json
import sys


def main():
    p = sys.argv[1]
    wo = f"projects/{p}/workflow-output"
    zpath = f"{wo}/zone3-{p}.json"
    try:
        z = json.load(open(zpath))
    except (OSError, ValueError) as e:
        sys.exit(f"FAIL zone-source: cannot read {zpath} ({e}) — run zone_detect "
                 f"with ZONE3_JSON_DIR={wo}")
    src = z.get("source")
    if not src or src == "unknown":
        sys.exit(f"FAIL zone-source: {zpath} carries no `source` stamp — it predates "
                 f"the scoped-mirror fix; re-run zone_detect")

    try:
        rules = (json.load(open(f"{wo}/scope-rules.json")) or {}).get("rules") or []
    except (OSError, ValueError):
        rules = []
    if rules and src != "scoped-mirror":
        print(f"FAIL zone-source [{p}]")
        print(f"  - {len(rules)} scope rule(s) declared "
              f"({', '.join(r.get('id', '?') for r in rules[:4])}) but the zone model "
              f"was built from '{src}' — excluded DOM is being identified as components")
        sys.exit(1)
    print(f"PASS zone-source: model built from '{src}' with {len(rules)} scope rule(s) "
          f"declared ({z.get('npages')} page(s), regime: {z.get('regime')})")


if __name__ == "__main__":
    main()
