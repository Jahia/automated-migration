#!/usr/bin/env bash
# content-extract.sh — Content extraction gate.
#
# Verifies that content-data.json was produced with real text content.
#
# Usage: content-extract.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
out="$proj/workflow-output"

[ -s "$out/content-data.json" ] || fail "content-extract: $out/content-data.json missing or empty"
[ -s "$out/component-manifest.json" ] || fail "content-extract: $out/component-manifest.json missing (run component-model first)"

python3 - "$proj" <<'PY'
import json, sys

proj = sys.argv[1]
content = json.load(open(f"{proj}/workflow-output/content-data.json"))
manifest = json.load(open(f"{proj}/workflow-output/component-manifest.json"))

valid_types = {c["name"] for c in manifest.get("components", [])}
pages = content.get("pages", {})

if not pages:
    print("FAIL: content-data.json has 0 pages"); sys.exit(1)

# home must have instances
home = pages.get("home", {})
home_instances = home.get("instances", [])
if not home_instances:
    print("FAIL: home page has 0 content instances"); sys.exit(1)

# total text length
total_chars = 0
errors = []
for page, data in pages.items():
    for inst in data.get("instances", []):
        ctype = inst.get("componentType", "?")
        if ctype not in valid_types:
            errors.append(f"  {page}/{inst.get('instanceName','?')}: componentType '{ctype}' not in manifest")
        for val in inst.get("fields", {}).values():
            if isinstance(val, str):
                total_chars += len(val)

if errors:
    print("FAIL: content references unknown component types:")
    for e in errors: print(e)
    sys.exit(1)

if total_chars < 500:
    print(f"FAIL: only {total_chars} chars of real text (need >= 500)"); sys.exit(1)

print(f"  pages: {len(pages)}")
print(f"  home instances: {len(home_instances)}")
print(f"  total text: {total_chars} chars")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "content-extract: validation failed"
pass "content-extract: content-data.json valid with real text"
