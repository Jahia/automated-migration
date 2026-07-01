#!/usr/bin/env bash
# asset-inventory.sh — Asset inventory gate.
#
# Verifies that asset-inventory.json was produced with images.
#
# Usage: asset-inventory.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
out="$proj/workflow-output"

[ -s "$out/asset-inventory.json" ] || fail "asset-inventory: $out/asset-inventory.json missing or empty"

python3 - "$proj" <<'PY'
import json, sys

proj = sys.argv[1]
data = json.load(open(f"{proj}/workflow-output/asset-inventory.json"))
images = data.get("images", [])

if not images:
    print("FAIL: asset-inventory.json has 0 images"); sys.exit(1)

# home must have images
home_imgs = [i for i in images if i.get("page") == "home"]
if not home_imgs:
    print("FAIL: home page has 0 images in inventory"); sys.exit(1)

# report
pages_with = len(set(i.get("page","") for i in images))
print(f"  total images: {len(images)}")
print(f"  pages with images: {pages_with}")
print(f"  home images: {len(home_imgs)}")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "asset-inventory: validation failed"
pass "asset-inventory: images catalogued"
