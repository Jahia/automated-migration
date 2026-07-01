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
# Pin the CANONICAL location every downstream consumer reads:
#   load_content.py, components-all.sh, template-govern.sh, inventory.sh all read
#   projects/<p>/workflow-output/component-manifest.json. A previous `find` here
#   accepted the manifest ANYWHERE under the project, so an analysis that wrote it
#   to a different subdir passed this gate while every consumer silently degraded
#   (components-all skips its drop guard on a missing manifest; load_content reads
#   {} and creates zero content). Producer path MUST equal consumer path.
out="$proj/workflow-output"
missing=""
for f in component-manifest.json content-data.json asset-inventory.json analysis.md; do
  if [ ! -s "$out/$f" ]; then
    # tolerate an off-path file but report it as a contract violation, not a pass
    stray=$(find "$proj" -name "$f" -size +1c 2>/dev/null | head -1)
    if [ -n "$stray" ]; then
      missing="$missing $f(found at $stray — must be at $out/$f)"
    else
      missing="$missing $f"
    fi
  fi
done
[ -z "$missing" ] || fail "analysis output(s) missing/off-path under $out:$missing (SKILL 01 Step 8 requires all 4 at the canonical workflow-output/ path consumers read)"
pass "all 4 analysis outputs present at canonical $out/"
