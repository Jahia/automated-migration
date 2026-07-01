#!/usr/bin/env bash
# pixel.sh — PIXEL-PARITY gate, run AT EACH PAGE CREATION (not end-of-run).
#
# A page-creation story is not done until every one of its pages passes a
# pixel-level diff against its captured reference (pixel-diff.mjs: both sides
# rendered in headless Chromium, dynamic noise frozen, per-pixel canvas diff).
# Writes ref/local/diff PNGs per page under
#   <project_path>/workflow-output/pixel/<slug>/
# so the agent/operator can SEE the gap and fix it before moving forward.
#
# STRICT on missing references: a page with no captured reference DOM cannot be
# verified pixel-perfect, so it FAILS (capture it, don't skip it).
#
# Optional per-project config orchestration/content/<project>.pixel-config.json:
#   { "maxDiffPct": 2.0,                 // threshold override
#     "hideSelectors": ["#didomi-host"]  // dynamic overlays to hide on BOTH sides
#   }
# The config is data (project-specific); this script is agnostic.
#
# Usage: pixel.sh <project_path> <siteKey> <lang> <pages | @sitemap_file> [maxDiffPct]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

proj="${1:?project_path required}"
site="${2:?siteKey required}"
lang="${3:?language required}"
pages_arg="${4:?pages or @sitemap file required}"
max_cli="${5:-}"
load_env "$proj"
project="$(basename "$proj")"

capdir="$proj/.reference/captured"
crawldir="$proj/.reference/cache/_crawl"
outroot="$proj/workflow-output/pixel"

# per-project config (threshold + overlay selectors + origin), CLI arg wins over config
cfg="orchestration/content/$project.pixel-config.json"
max_pct="2.0"; hide=""; ref_origin=""
if [ -f "$cfg" ]; then
  max_pct="$(python3 -c "import json;print(json.load(open('$cfg')).get('maxDiffPct',2.0))")"
  hide="$(python3 -c "import json;print('|'.join(json.load(open('$cfg')).get('hideSelectors',[])))")"
  ref_origin="$(python3 -c "import json;print(json.load(open('$cfg')).get('referenceOrigin',''))")"
fi
[ -n "$max_cli" ] && max_pct="$max_cli"

# reference origin for asset loading: derived from the crawl host dir (agnostic),
# config override wins. A file:// reference renders naked without it.
if [ -z "$ref_origin" ] && [ -d "$crawldir" ]; then
  host_dir="$(find "$crawldir" -mindepth 1 -maxdepth 1 -type d | head -1)"
  [ -n "$host_dir" ] && ref_origin="https://$(basename "$host_dir")"
fi

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

# Same reference resolution as fidelity-all.sh: browser capture first, then the
# wget crawl cache (SSR sites need no browser capture).
find_ref() {
  local p="${1#/}"; p="${p%.html}"; p="${p#sites/$site/}"; p="${p#home/}"
  [ -z "$p" ] && p="home"
  local cands=("${p//\//-}" "${p##*/}" "home")
  for c in "${cands[@]}"; do
    [ -f "$capdir/$c.html" ] && { echo "$capdir/$c.html"; return 0; }
  done
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

failed=(); noref=(); checked=0
for path in "${pages[@]}"; do
  p="${path#/}"; p="${p%.html}"
  case "$p" in
    sites/*) url="$JAHIA_HOST/$p.html" ;;
    home)    url="$JAHIA_HOST/sites/$site/home.html" ;;
    *)       url="$JAHIA_HOST/sites/$site/home/$p.html" ;;
  esac
  checked=$((checked+1))
  slug="$(echo "$p" | tr '/' '-')"
  # per-page threshold override (e.g. listing pages whose static reference cannot
  # render its client-side cards) — from pixel-config.json pageOverrides
  page_max="$max_pct"
  if [ -f "$cfg" ]; then
    ov="$(python3 -c "
import json
o=json.load(open('$cfg')).get('pageOverrides',{})
v=o.get('$p') or o.get('/$p') or {}
print(v.get('maxDiffPct',''))" 2>/dev/null)"
    [ -n "$ov" ] && page_max="$ov"
  fi
  if ref="$(find_ref "$path")"; then
    echo "── pixel: $url  vs  ${ref#$proj/}  (max ${page_max}%)"
    if node "$HERE/pixel-diff.mjs" "$(cd "$(dirname "$ref")" && pwd)/$(basename "$ref")" "$url" \
         "$outroot/$slug" "$page_max" "$hide" "$ref_origin" >/tmp/pixel-$$.json 2>/tmp/pixel-$$.err; then
      pct="$(python3 -c "import json;print(json.load(open('/tmp/pixel-$$.json'))['diffPct'])" 2>/dev/null || echo "?")"
      echo "   PASS  diff=${pct}%  → $outroot/$slug/{ref,local,diff}.png"
    else
      pct="$(python3 -c "import json;print(json.load(open('/tmp/pixel-$$.json'))['diffPct'])" 2>/dev/null || echo "?")"
      echo "   FAIL  diff=${pct}% (> ${page_max}%)  → inspect $outroot/$slug/diff.png"
      head -3 /tmp/pixel-$$.err 2>/dev/null | sed 's/^/     /'
      failed+=("$p (${pct}%)")
    fi
  else
    echo "── $url  → NO captured reference — cannot verify pixel parity"
    noref+=("$p")
  fi
done
rm -f /tmp/pixel-$$.json /tmp/pixel-$$.err

echo "pixel: $checked page(s) checked, ${#failed[@]} over threshold, ${#noref[@]} without reference"
if [ "${#noref[@]}" -gt 0 ]; then
  fail "pixel: ${#noref[@]} page(s) have NO reference DOM (capture them — a page without a reference cannot be pixel-verified): ${noref[*]}"
fi
if [ "${#failed[@]}" -gt 0 ]; then
  fail "pixel: ${#failed[@]}/$checked page(s) exceed their pixel-diff threshold — fix each page before moving forward: ${failed[*]}"
fi
pass "pixel: all $checked page(s) within their pixel-diff threshold"
