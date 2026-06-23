#!/usr/bin/env bash
# Step 4 probe: content types build clean, namespace present, i18n bundles exist.
# Usage: cnd.sh <project_path> <namespace>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:?namespace required}"
require_node 20
( cd "$proj" && yarn build )
cnd=$(find "$proj/settings" -name 'definitions.cnd' 2>/dev/null | head -1)
[ -n "$cnd" ] || fail "definitions.cnd not found under $proj/settings"
grep -q "$ns" "$cnd" || fail "namespace '$ns' not declared in $cnd"
find "$proj/settings" -name '*_en.properties' 2>/dev/null | grep -q . || fail "no *_en.properties"
find "$proj/settings" -name '*_fr.properties' 2>/dev/null | grep -q . || fail "no *_fr.properties"
pass "build clean; '$ns' in $cnd; en+fr properties present"
