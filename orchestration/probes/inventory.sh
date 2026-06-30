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
  # The baseline must be the full APPROVED ANALYSIS scope, not just what is
  # implemented at freeze time. The recovered components are approved at Gate 1
  # but get their CND later (implementation step); freezing from the filesystem
  # alone would (a) reject them as "new types" via no-new-types and (b) leave the
  # coverage gate blind. So fold in every nodeType + child type from the manifest.
  manifest="$proj/workflow-output/component-manifest.json"
  if [ -f "$manifest" ]; then
    mtypes="$(python3 - "$manifest" <<'PY'
import json, sys
m = json.load(open(sys.argv[1])); out = set()
for c in m.get("components", []):
    nt = c.get("nodeType")
    if nt: out.add(nt)
    ct = c.get("childType"); cts = list(c.get("childTypes") or [])
    if isinstance(ct, str): cts.append(ct)
    for t in cts:
        if isinstance(t, str) and ":" in t: out.add(t)
    for ch in (c.get("children") or []):
        if isinstance(ch, dict) and ch.get("nodeType"): out.add(ch["nodeType"])
for t in sorted(out): print(t)
PY
)"
    types="$(printf '%s\n%s\n' "$types" "$mtypes" | grep -E "^${ns}:" | sort -u)"
  fi
  printf '%s\n' "$types" > "$out"
  echo "wrote $(printf '%s\n' "$types" | grep -c . ) types to $out (filesystem + approved manifest)"
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
