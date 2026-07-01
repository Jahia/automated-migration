#!/usr/bin/env bash
# html-fragments.sh — HTML fragments gate.
#
# Verifies that every component/view in the manifest has a corresponding
# HTML fragment file in workflow-output/html-fragments/.
#
# Usage: html-fragments.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
out="$proj/workflow-output"
fragdir="$out/html-fragments"

[ -s "$out/component-manifest.json" ] || fail "html-fragments: $out/component-manifest.json missing (run component-model first)"
[ -d "$fragdir" ] || fail "html-fragments: $fragdir/ directory missing"

python3 - "$proj" <<'PY'
import json, os, sys

proj = sys.argv[1]
fragdir = f"{proj}/workflow-output/html-fragments"
m = json.load(open(f"{proj}/workflow-output/component-manifest.json"))
components = m.get("components", [])

missing = []
empty = []
no_class = []

for c in components:
    name = c.get("name", "?")
    for v in c.get("views", []):
        vname = v.get("name", "default")
        fname = f"{name}.{vname}.html"
        fpath = os.path.join(fragdir, fname)
        if not os.path.isfile(fpath):
            missing.append(f"  {fname}")
        else:
            content = open(fpath).read()
            if len(content.strip()) < 50:
                empty.append(f"  {fname}: {len(content)} chars (too short)")
            elif 'class=' not in content:
                no_class.append(f"  {fname}: no class= attributes found")

errors = missing + empty + no_class
if errors:
    print("FAIL: html-fragments issues:")
    for e in errors: print(e)
    sys.exit(1)

total = sum(len(c.get("views",[])) for c in components)
files = len([f for f in os.listdir(fragdir) if f.endswith(".html")])
print(f"  fragments: {files} files for {total} component/views")
print(f"  all fragments contain real CSS classes")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "html-fragments: validation failed"
pass "html-fragments: all component/view fragments present"
