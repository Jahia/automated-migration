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
  fail "template-govern: ${#unrestricted[@]} area(s) accept ANY content — add allowedNodeTypes to restrict each region (a restricted slot or an OPEN gridRow-led palette — both are fine, a free-for-all is not)"
fi
# soft nudge: an OPEN composition surface should include the gridRow layout primitive.
# (file-level heuristic — open areas reference a broad palette const we don't resolve here.)
for f in "${pages[@]}"; do
  grep -q "allowedNodeTypes" "$f" || continue
  grep -qiE ":gridRow|gridRow" "$f" || echo "  note: ${f#$proj/} restricts areas but references no gridRow — open composition surfaces need the gridRow layout primitive" >&2
done

# ── shared-region (AbsoluteArea) governance ───────────────────────────────────
# Every component the analysis marks areaType=absolute (site chrome: nav, footer,
# top bar) is SHARED across all pages and must be placed once as an <AbsoluteArea>
# (in Layout or a template) — otherwise it never renders (the "topNav is missing"
# bug: a shared component modelled but never placed). And a shared region must be
# EDITABLE: readOnly="children" on it blanks/locks it in Page Builder so editors
# can't manage nav/footer content. Check both against the manifest.
manifest="$proj/workflow-output/component-manifest.json"
absdecl="$(grep -rhoE '<AbsoluteArea[^>]*nodeType="[^"]+"' "$tdir" 2>/dev/null | grep -oE 'nodeType="[^"]+"' | sed 's/nodeType="//; s/"//' | sort -u)"
if [ -f "$manifest" ]; then
  absreq="$(python3 - "$manifest" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
for c in m.get("components", []):
    if c.get("areaType") == "absolute" and c.get("nodeType"):
        print(c["nodeType"])
PY
)"
  unplaced="$(comm -23 <(printf '%s\n' "$absreq" | sort -u | grep -v '^$') <(printf '%s\n' "$absdecl" | sort -u | grep -v '^$') || true)"
  if [ -n "$unplaced" ]; then
    echo "Shared (areaType=absolute) components not placed as an <AbsoluteArea>:" >&2
    printf '  ✗ %s\n' $unplaced >&2
    fail "template-govern: $(printf '%s\n' "$unplaced" | grep -c .) shared component(s) modelled but never placed — add <AbsoluteArea nodeType=\"<type>\" parent={homePage}/> in Layout (like nav/footer). A shared component that is never placed never renders."
  fi
fi
# readOnly on a shared region locks editing — never on nav/footer/topbar AbsoluteAreas
ro="$(grep -rnE '<AbsoluteArea[^>]*readOnly' "$tdir" 2>/dev/null | sed "s#$proj/##")"
if [ -n "$ro" ]; then
  echo "AbsoluteArea with readOnly (shared region not editable in Page Builder):" >&2
  printf '  ✗ %s\n' "$ro" >&2
  fail "template-govern: shared AbsoluteArea uses readOnly — remove it so editors can manage nav/footer/top-bar content in Page Builder"
fi

pass "template-govern: $npages page template(s) + MainResource; every Area declares allowedNodeTypes; shared (absolute) components placed + editable"
