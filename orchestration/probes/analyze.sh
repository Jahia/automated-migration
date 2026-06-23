#!/usr/bin/env bash
# Step 1 probe: analysis artifacts exist and are non-empty.
# Usage: analyze.sh <project_path>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
m=$(find "$proj" -name component-manifest.json -size +1c 2>/dev/null | head -1)
c=$(find "$proj" -name content-data.json -size +1c 2>/dev/null | head -1)
[ -n "$m" ] || fail "component-manifest.json missing or empty under $proj"
[ -n "$c" ] || fail "content-data.json missing or empty under $proj"
pass "manifest=$m content=$c"
