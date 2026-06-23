#!/usr/bin/env bash
# Step 8 probe: Layout has header + footer AbsoluteArea.
# Usage: templates.sh <project_path>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
layout=$(find "$proj/src" -name 'Layout*.tsx' 2>/dev/null | head -1)
[ -n "$layout" ] || fail "no Layout.tsx in $proj/src"
n=$(grep -c 'AbsoluteArea' "$layout" || true)
[ "${n:-0}" -ge 2 ] || fail "expected >=2 AbsoluteArea (header+footer), found ${n:-0} in $layout"
pass "$n AbsoluteArea in $layout"
