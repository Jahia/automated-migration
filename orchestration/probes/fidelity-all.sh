#!/usr/bin/env bash
# fidelity-all.sh — per-page structural-fidelity gate for a whole site.
#
# Runs fidelity-live.sh on EVERY page that has a captured reference DOM, so the
# JS-rendered diff (sections + listing/card counts + facet values) fires per page
# instead of as one end-of-run sweep. It pairs each live page with its persisted
# browser capture at projects/<p>/.reference/captured/<slug>.html (written by the
# capture-reference skill). Fails on the FIRST page that is materially below its
# reference and names it.
#
# A page WITHOUT a captured reference is reported as "no reference (skipped)" and
# counted — never silently passed. If NO page has a reference at all, the gate
# fails: capture-reference never ran, so fidelity was never actually checked.
#
# Usage:
#   fidelity-all.sh <project_path> <siteKey> <lang> <pages | @sitemap_file>
# e.g.
#   orchestration/probes/fidelity-all.sh projects/supercar-garage supercar-garage fr \
#     @orchestration/sitemaps/supercar-garage.txt
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

proj="${1:?project_path required}"
site="${2:?siteKey required}"
lang="${3:?language required}"
pages_arg="${4:?pages or @sitemap file required}"
load_env "$proj"

capdir="$proj/.reference/captured"
# SSR sites need no browser capture: the wget crawl cache IS the server-rendered
# reference DOM. fall back to it when captured/ is absent or has no match.
crawldir="$proj/.reference/cache/_crawl"

# Resolve the page list: @file → read lines (strip comments/CR), else split commas.
pages=()
if [[ "$pages_arg" == @* ]]; then
  file="${pages_arg#@}"
  [ -f "$file" ] || fail "sitemap file not found: $file"
  while IFS= read -r line; do
    line="$(echo "$line" | tr -d '\r' | sed 's/#.*//' | xargs)"
    [ -n "$line" ] && pages+=("$line")
  done < "$file"
else
  IFS=',' read -r -a pages <<< "$pages_arg"
fi
[ "${#pages[@]}" -gt 0 ] || fail "no pages resolved from: $pages_arg"

# For a page path, find its captured reference .html by trying, in order:
#   full-path-with-slashes-as-dashes, last segment, 'home'.
find_ref() {
  local p="${1#/}"; p="${p%.html}"; p="${p#sites/$site/}"; p="${p#home/}"
  [ -z "$p" ] && p="home"
  local cands=("${p//\//-}" "${p##*/}" "home")
  for c in "${cands[@]}"; do
    [ -f "$capdir/$c.html" ] && { echo "$capdir/$c.html"; return 0; }
  done
  # SSR fallback: locate the page in the wget crawl cache by slug.
  # home → the crawl root (<host>/<lang>.html); else first match for <slug>.html.
  if [ -d "$crawldir" ]; then
    local slug="${p##*/}"
    if [ "$p" = "home" ]; then
      local hit; hit="$(find "$crawldir" -maxdepth 2 -name '*.html' 2>/dev/null \
        | grep -E '/[a-z]{2}(-[A-Z]{2})?\.html$' | head -1)"
      [ -n "$hit" ] && { echo "$hit"; return 0; }
    fi
    local hit; hit="$(find "$crawldir" -name "$slug.html" 2>/dev/null | head -1)"
    [ -n "$hit" ] && { echo "$hit"; return 0; }
  fi
  return 1
}

failed=(); skipped=(); gated=0; checked=0
for path in "${pages[@]}"; do
  p="${path#/}"; p="${p%.html}"
  case "$p" in
    sites/*) url="$JAHIA_HOST/$p.html" ;;
    home)    url="$JAHIA_HOST/sites/$site/home.html" ;;
    *)       url="$JAHIA_HOST/sites/$site/home/$p.html" ;;
  esac
  checked=$((checked+1))
  if ref="$(find_ref "$path")"; then
    echo "── fidelity-live: $url  vs  ${ref#$proj/}"
    if bash "$HERE/fidelity-live.sh" "$ref" "$url" >/tmp/fidelity-all-$$.log 2>&1; then
      echo "   PASS"; gated=$((gated+1))
    else
      echo "   FAIL"; sed -n '1,14p' /tmp/fidelity-all-$$.log | sed 's/^/     /'
      failed+=("$url"); gated=$((gated+1))
    fi
  else
    echo "── $url  → no captured reference (skipped)"
    skipped+=("$path")
  fi
done
rm -f /tmp/fidelity-all-$$.log

echo "fidelity-all: $checked page(s) — $gated gated, ${#skipped[@]} without a reference"
[ "${#skipped[@]}" -gt 0 ] && echo "  no reference for: ${skipped[*]}"

if [ "$gated" -eq 0 ]; then
  fail "fidelity-all: NO page had a reference DOM under $capdir or the crawl cache $crawldir — neither capture-reference nor the wget crawl produced reference HTML, so fidelity was never checked. Capture/crawl the reference first."
fi
if [ "${#failed[@]}" -gt 0 ]; then
  fail "fidelity-all: ${#failed[@]}/$gated gated page(s) are materially below the reference: ${failed[*]}"
fi
pass "fidelity-all: all $gated gated page(s) match the reference (${#skipped[@]} had no capture)"
