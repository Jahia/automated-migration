#!/usr/bin/env bash
# Reuse guard: fail if the module declares any content type NOT in the approved
# baseline. New VIEWS (additional .server.tsx on an existing type) add no type
# and pass freely. A genuinely new type is allowed only as a deliberate baseline
# update (re-run inventory.sh --write after the operator approves it).
# Usage: no-new-types.sh <project_path> <namespace> <baseline_file>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:?namespace required}"
base="${3:?baseline file required}"
[ -f "$base" ] || fail "baseline not found: $base (generate with inventory.sh --write)"
current=$(grep -rhoE "\[${ns}:[a-zA-Z0-9]+\]" "$proj/src" "$proj/settings" 2>/dev/null | tr -d '[]' | sort -u)
new=$(comm -23 <(printf '%s\n' "$current") <(sort -u "$base") || true)
if [ -n "$new" ]; then
  echo "New component types introduced - reuse an existing type or add a view instead:" >&2
  printf '  %s\n' $new >&2
  fail "$(printf '%s\n' "$new" | grep -c .) new ${ns}: type(s); content/page-discovery must reuse the baseline"
fi
pass "no new ${ns}: types beyond baseline ($(printf '%s\n' "$current" | grep -c .) types)"
