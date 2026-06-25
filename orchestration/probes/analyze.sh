#!/usr/bin/env bash
# Step 1 probe: analysis artifacts exist and are non-empty.
# Enforces the 4 output files SKILL 01 Step 8 requires (previously only 2 were
# checked, so a thin analysis missing the image catalogue passed the gate).
# Usage: analyze.sh <project_path>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
missing=""
for f in component-manifest.json content-data.json asset-inventory.json analysis.md; do
  found=$(find "$proj" -name "$f" -size +1c 2>/dev/null | head -1)
  [ -n "$found" ] || missing="$missing $f"
done
[ -z "$missing" ] || fail "required analysis output(s) missing or empty under $proj:$missing (SKILL 01 Step 8 requires all 4)"
pass "all 4 analysis outputs present under $proj"
