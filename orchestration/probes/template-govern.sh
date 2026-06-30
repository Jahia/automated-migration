#!/usr/bin/env bash
# template-govern.sh — page-template governance gate.
#
# Templates are the contribution contract: a small set of page skeletons (home /
# section / detail) whose editable Areas RESTRICT what content can be dropped where
# (Area `allowedNodeTypes`). This gate checks:
#   1. a sane number of page templates exist (2–6) — enough to differentiate roles
#      (landing / standard / detail), few enough to guide contribution;
#   2. every page-template <Area> declares allowedNodeTypes (so the region is guided,
#      not a free-for-all). Shared regions live in Layout as AbsoluteAreas (locked) and
#      are not counted here.
#
# Usage: template-govern.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
tdir="$proj/src/templates"
[ -d "$tdir" ] || fail "no src/templates in $proj"

# page templates (jnt:page); MainResource detail template is separate (renders fullPage)
mapfile_pages() { find "$tdir/Page" -name '*.server.tsx' 2>/dev/null; }
pages=(); while IFS= read -r f; do [ -n "$f" ] && pages+=("$f"); done < <(mapfile_pages)
npages="${#pages[@]}"
has_mainresource=0
[ -n "$(find "$tdir/MainResource" -name '*.server.tsx' 2>/dev/null | head -1)" ] && has_mainresource=1

echo "page templates: $npages  + MainResource detail template: $has_mainresource"
[ "$npages" -ge 1 ] || fail "no page templates under $tdir/Page — need at least home + a standard page"
if [ "$npages" -lt 2 ]; then
  echo "  note: only $npages page template — most sites need at least home + a standard/section template" >&2
fi
[ "$npages" -le 6 ] || echo "  note: $npages page templates — more than ~4 usually means content variety that belongs in views, not templates" >&2

# every <Area> in a page template must declare allowedNodeTypes
unrestricted=()
for f in "${pages[@]}"; do
  rel="${f#$proj/}"
  # each <Area …/> occurrence (single-line in our templates) must carry allowedNodeTypes
  while IFS= read -r line; do
    echo "$line" | grep -q "allowedNodeTypes" || unrestricted+=("$rel: $(echo "$line" | grep -oE '<Area[^>]*name=[^ ]+' | head -1)")
  done < <(grep -hoE "<Area\b[^>]*>|<Area\b[^/]*/>" "$f" 2>/dev/null)
done

if [ "${#unrestricted[@]}" -gt 0 ]; then
  echo "Unrestricted page-template areas (no allowedNodeTypes — contribution not guided):"
  printf '  ✗ %s\n' "${unrestricted[@]}"
  fail "template-govern: ${#unrestricted[@]} area(s) accept ANY content — add allowedNodeTypes to restrict each region"
fi
pass "template-govern: $npages page template(s) + MainResource; every Area restricts its content (allowedNodeTypes)"
