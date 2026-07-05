#!/usr/bin/env bash
# component-discover.sh — Component discovery output gate.
#
# Verifies that component-candidates.json exists and has valid structure.
# Does NOT make discovery decisions — that's the LLM's job based on
# the extracted blocks from html-blocks.json.
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
    if freq < 1:
        errors.append(f"  {cid}: frequency={freq} (must be >= 1)")
    # dataShape can be empty for structural components — that's valid
    # The LLM decides what's structural vs content, not this probe

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
