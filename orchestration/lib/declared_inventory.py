#!/usr/bin/env python3
"""declared_inventory.py — the source's OWN component declaration, when it has one.

Some CMSs declare every component boundary + field in the rendered DOM. Reading
that declaration is strictly better than inferring boundaries: it is complete and
reproducible. The #1 analysis defect on such a source is the opposite — eyeballing
the render and silently dropping the small peripheral components (a top-bar, a
contact block, key figures): on lesalondelaphoto the LLM manifest held 14 of the
source's 42 declared types.

So: run the CMS adapter when the detected source has one, and record the result as
the coverage contract (`probes/sxa-coverage.sh` later fails on any declared type the
component model neither maps nor explicitly ignores). When the source declares
nothing, say so plainly and let the inferential path (zone_detect + segmentation)
carry the identification — never fail, never fake an inventory.

Adapters: sitecore-sxa (div.component / component-content / field-*). Drupal
(paragraph--type-*), AEM (data-sly / cq), explicit data-component sources plug in
the same way.

Writes projects/<p>/.reference/declared-components.json (+ the historical
.reference/sxa-components.json name for the SXA coverage gate).
Usage: declared_inventory.py <project>
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADAPTERS = {"sitecore-sxa": "sxa-extract.py"}


def main():
    p = sys.argv[1]
    src = "generic"
    try:
        src = json.load(open(f"orchestration/{p}.source.json")).get("source", "generic")
    except (OSError, ValueError):
        print(f"declared_inventory: no orchestration/{p}.source.json — run "
              f"source_detect.py first; assuming generic")
    ref = f"projects/{p}/.reference"
    os.makedirs(ref, exist_ok=True)
    out = f"{ref}/declared-components.json"
    adapter = ADAPTERS.get(src)
    if not adapter:
        json.dump({"adapter": "none", "source": src, "componentTypeCount": 0,
                   "components": [],
                   "note": "this source declares no component boundaries in the DOM; "
                           "identification rests on zone_detect + segmentation"},
                  open(out, "w"), indent=1)
        print(f"declared_inventory: source '{src}' has no declaring adapter -> {out} "
              f"(0 declared types; inferential path only)")
        return

    crawl = f"projects/{p}/.reference/cache/_crawl"
    if not os.path.isdir(crawl):
        sys.exit(f"FAIL declared_inventory: no crawl cache at {crawl}")
    r = subprocess.run([sys.executable, os.path.join(HERE, adapter), crawl],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(f"FAIL declared_inventory: {adapter} exited {r.returncode} "
                 f"{r.stderr[:200]}")
    data = json.loads(r.stdout)
    data["adapter"] = src
    json.dump(data, open(out, "w"), indent=2, ensure_ascii=False)
    # the SXA coverage gate reads the historical filename
    if src == "sitecore-sxa":
        json.dump(data, open(f"{ref}/sxa-components.json", "w"), indent=2,
                  ensure_ascii=False)
    n = data.get("componentTypeCount", 0)
    cont = sum(1 for c in data.get("components", []) if c.get("isContainer"))
    print(f"declared_inventory: adapter '{src}' -> {n} declared component type(s) "
          f"({cont} container(s)) -> {out}")
    for c in data.get("components", [])[:12]:
        print(f"  x{c['instances']:<4} {c['type']:<30} "
              f"{'CONTAINER ' if c.get('isContainer') else ''}"
              f"{len(c.get('fields', []))} field(s)")


if __name__ == "__main__":
    main()
