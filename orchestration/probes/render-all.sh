#!/usr/bin/env bash
# render-all.sh — per-page render gate for a whole site.
#
# Runs render-truth.sh on EVERY page, so the visual/diff check fires at each
# page's creation step — not as a single sweep at the end of the migration.
# A page is done only when it renders clean; this fails the step on the FIRST
# page with a render defect and reports which one.
#
# Usage:
#   render-all.sh <project_path> <siteKey> <lang> <pages | @sitemap_file>
# e.g.
#   orchestration/probes/render-all.sh projects/supercar-garage supercar-garage fr \
#     @orchestration/sitemaps/supercar-garage.txt
#   orchestration/probes/render-all.sh projects/acme acme en /home,/home/news,/home/about
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

proj="${1:?project_path required}"
site="${2:?siteKey required}"
lang="${3:?language required}"
pages_arg="${4:?pages or @sitemap file required}"
load_env "$proj"

# Resolve the page list: @file → read lines, else split on commas.
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

failed=()
checked=0
for path in "${pages[@]}"; do
  # normalize to a live render URL: $HOST/sites/<site><path>.html
  p="${path#/}"; p="${p%.html}"
  case "$p" in
    sites/*) url="$JAHIA_HOST/$p.html" ;;
    home)    url="$JAHIA_HOST/sites/$site/home.html" ;;
    *)       url="$JAHIA_HOST/sites/$site/home/$p.html" ;;
  esac
  echo "── render-truth: $url"
  if bash "$HERE/render-truth.sh" "$url" >/tmp/render-all-$$.log 2>&1; then
    echo "   PASS"
  else
    echo "   FAIL"; sed -n '1,12p' /tmp/render-all-$$.log | sed 's/^/     /'
    failed+=("$url")
  fi
  checked=$((checked+1))
done
rm -f /tmp/render-all-$$.log

if [ "${#failed[@]}" -gt 0 ]; then
  fail "render-all: ${#failed[@]}/$checked page(s) have render defects: ${failed[*]}"
fi
pass "render-all: all $checked page(s) render clean"
