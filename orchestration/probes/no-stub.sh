#!/usr/bin/env bash
# no-stub.sh — FAIL when a component view is a stub / placeholder.
#
# The supercar "fiasco" had 29/32 views stubbed while the build still passed.
# This gate fails when any `*.server.tsx` view is empty, returns null, has a
# TODO/placeholder marker, or emits no JSX — i.e. the loop generated a shell it
# never filled. Also flags CND node types that have NO registered view.
#
# Usage: no-stub.sh <project_path> [namespace]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:-}"
src="$proj/src"
[ -d "$src" ] || fail "no src/ in $proj"

stubs=()
while IFS= read -r f; do
  # only real component views (registered with jahiaComponent)
  grep -q "jahiaComponent" "$f" || continue
  tags=$(grep -oE '<[A-Za-z][A-Za-z0-9.]*' "$f" | wc -l | tr -d ' ')
  # TODO/FIXME/"not implemented"/"coming soon" as real markers (NOT the HTML
  # `placeholder=` attribute, which is legit). Match whole words / phrases.
  marker=$(grep -ciE '\b(TODO|FIXME)\b|not implemented|coming soon' "$f")
  reason=""
  if [ "$marker" -gt 0 ]; then reason="TODO/FIXME/not-implemented marker"
  elif [ "$tags" -eq 0 ]; then reason="emits no JSX (returns null/empty — never filled)"
  fi
  [ -n "$reason" ] && stubs+=("${f#$proj/}  — $reason")
done < <(find "$src/components" -name '*.server.tsx' 2>/dev/null)

# CND node types with no registered view (declared but never rendered)
typeless=()
if [ -n "$ns" ]; then
  while IFS= read -r t; do
    grep -rqE "nodeType:[[:space:]]*[\"']${ns}:${t}[\"']" "$src" 2>/dev/null || typeless+=("$ns:$t (no view registers it)")
  done < <(grep -rhoE "^\[${ns}:[a-zA-Z0-9]+\]" "$src" 2>/dev/null | sed -E "s/^\[${ns}:([a-zA-Z0-9]+)\]/\1/" | sort -u)
fi

if [ "${#stubs[@]}" -gt 0 ] || [ "${#typeless[@]}" -gt 0 ]; then
  echo "Stub / incomplete views:"; printf '  - %s\n' "${stubs[@]}"
  [ "${#typeless[@]}" -gt 0 ] && { echo "Node types with no view:"; printf '  - %s\n' "${typeless[@]}"; }
  fail "no-stub: ${#stubs[@]} stub view(s) + ${#typeless[@]} viewless type(s) — the loop left shells unfilled"
fi
pass "no-stub: every view emits real markup; every $ns: type has a view"
