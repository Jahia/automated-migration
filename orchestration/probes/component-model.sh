#!/usr/bin/env bash
# component-model.sh — CND component model gate.
#
# Verifies the final component-manifest.json: namespace, views, no duplicate
# shapes, jmix:mainResource has both views.
#
# Usage: component-model.sh <project_path> <namespace>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:?namespace required}"
out="$proj/workflow-output"

[ -s "$out/component-manifest.json" ] || fail "component-model: $out/component-manifest.json missing or empty"

# 1. Namespace check
python3 - "$proj" "$ns" <<'PY'
import json, sys

proj, ns = sys.argv[1], sys.argv[2]
m = json.load(open(f"{proj}/workflow-output/component-manifest.json"))
components = m.get("components", [])

if not components:
    print("FAIL: 0 components in manifest"); sys.exit(1)

errors = []
for c in components:
    ntype = c.get("nodeType", "")
    name = c.get("name", "?")
    views = c.get("views", [])

    # namespace check
    if not ntype.startswith(ns + ":"):
        errors.append(f"  {name}: nodeType '{ntype}' doesn't use namespace '{ns}'")

    # at least 1 view
    if not views:
        errors.append(f"  {name}: no views defined")

    # jmix:mainResource must have default + fullPage
    if c.get("needsMainResource"):
        view_names = [v.get("name","") for v in views]
        for req in ["default", "fullPage"]:
            if req not in view_names:
                errors.append(f"  {name}: jmix:mainResource missing '{req}' view")

if errors:
    print("FAIL: manifest validation errors:")
    for e in errors: print(e)
    sys.exit(1)

print(f"  components: {len(components)}")
for c in components:
    views = [v["name"] for v in c.get("views",[])]
    print(f"    {c['nodeType']}: {len(views)} views ({', '.join(views)})")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "component-model: namespace/view validation failed"

# 2. Duplicate shapes check
bash "$HERE/dup-shapes.sh" "$proj" "$ns" || fail "component-model: duplicate property shapes found"
pass "component-model: manifest valid, namespace correct, no duplicate shapes"
