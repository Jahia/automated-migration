#!/usr/bin/env bash
# component-discover.sh — Component discovery gate.
#
# Verifies that component candidates were discovered with valid data shapes.
#
# Usage: component-discover.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
out="$proj/workflow-output"

[ -s "$out/component-candidates.json" ] || fail "component-discover: $out/component-candidates.json missing or empty"

python3 - "$proj" <<'PY'
import json, sys

proj = sys.argv[1]
data = json.load(open(f"{proj}/workflow-output/component-candidates.json"))
components = data.get("components", [])

if not components:
    print("FAIL: 0 component candidates"); sys.exit(1)

errors = []
for c in components:
    cid = c.get("candidateId", "?")
    freq = c.get("frequency", 0)
    shape = c.get("dataShape", [])
    if freq < 1:
        errors.append(f"  {cid}: frequency={freq} (must be >= 1)")
    # Allow empty shape only if it's a structural component (no content fields)
    if not shape:
        # These are valid structural components without detectable content
        structural_types = {"raw-html", "background-image", "carousel", "video", "video-content-block", "container", "facet-aggregated", "load-more", "facet-dropdown", "unknown", "form", "search"}
        if cid not in structural_types:
            errors.append(f"  {cid}: empty dataShape")

if errors:
    print("FAIL: invalid component candidates:")
    for e in errors: print(e)
    sys.exit(1)

cross = [c for c in components if c.get("isCrossCutting")]
main_res = [c for c in components if c.get("isMainResource")]
print(f"  candidates: {len(components)}")
print(f"  crossCutting: {len(cross)}")
print(f"  mainResource: {len(main_res)}")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "component-discover: validation failed"
pass "component-discover: candidates valid"
