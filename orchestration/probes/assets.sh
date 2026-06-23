#!/usr/bin/env bash
# Step 3 probe: static assets imported and Layout references a stylesheet.
# Usage: assets.sh <project_path>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
test -d "$proj/static" || fail "no static/ dir in $proj"
ncss=$(find "$proj/static" -name '*.css' 2>/dev/null | wc -l | tr -d ' ')
[ "${ncss:-0}" -ge 1 ] || fail "no .css files under $proj/static"
layout=$(find "$proj/src" -name 'Layout*.tsx' 2>/dev/null | head -1)
[ -n "$layout" ] || fail "no Layout.tsx in $proj/src"
grep -qiE '\.css|fontawesome|cdn|stylesheet' "$layout" || fail "Layout references no stylesheet"
pass "$ncss css in static; Layout=$layout references styles"
