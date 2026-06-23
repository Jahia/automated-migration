#!/usr/bin/env bash
# Component reuse catalog: list the module's content types and their views.
# This is the list a page-discovery agent MUST map onto before inventing anything.
# Usage:
#   inventory.sh <project_path> <namespace>                 # print catalog
#   inventory.sh <project_path> <namespace> --write <file>  # write sorted type list (baseline)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:?namespace required}"

# All [<ns>:type] declarations across CND + .tsx definitions, de-duplicated.
types=$(grep -rhoE "\[${ns}:[a-zA-Z0-9]+\]" "$proj/src" "$proj/settings" 2>/dev/null \
        | tr -d '[]' | sort -u)
[ -n "$types" ] || fail "no ${ns}: types found under $proj"

if [ "${3:-}" = "--write" ]; then
  out="${4:?output file required after --write}"
  mkdir -p "$(dirname "$out")"
  printf '%s\n' "$types" > "$out"
  echo "wrote $(printf '%s\n' "$types" | grep -c . ) types to $out"
  exit 0
fi

echo "== ${ns}: content types (reuse these; add a view before a new type) =="
while IFS= read -r t; do
  short="${t#${ns}:}"
  # views = *.server.tsx / *.client.tsx in a dir whose name loosely matches the type
  views=$(find "$proj/src" -type f \( -name '*.server.tsx' -o -name '*.client.tsx' \) \
          2>/dev/null | grep -iE "/${short}/" | sed 's#.*/##' | paste -sd', ' - || true)
  printf '  %-28s %s\n' "$t" "${views:-(view dir name differs)}"
done <<< "$types"
echo "Total: $(printf '%s\n' "$types" | grep -c .) types"
