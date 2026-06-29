#!/usr/bin/env bash
# site-review.sh — a11y (axe-core) + SEO scoring gate (from @jahia/agentic).
#
# Runs the agentic `review-pages.mjs` over every page: scores accessibility
# (WCAG 2.1 AA via axe-core) and checks SEO basics (title, meta description,
# single h1, img alt). FAILS on any critical/serious a11y violation or missing
# SEO baseline. Complements render-truth.sh (layout/visibility) with a11y/SEO.
#
# Usage: site-review.sh <project_path> <siteKey> <lang> <pages | @sitemap_file>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"; site="${2:?siteKey required}"
lang="${3:?language required}"; pages_arg="${4:?pages or @sitemap required}"
load_env "$proj"; require_node 18

ROOT="$(cd "$HERE/../.." && pwd)"
SCRIPT="$ROOT/.agents/skills/dev/jahia-dev-site-review/scripts/review-pages.mjs"
[ -f "$SCRIPT" ] || fail "review-pages.mjs not found — run .agents/agentic-sync.sh to pull the agentic skills"

# resolve pages → live URLs
pages=()
if [[ "$pages_arg" == @* ]]; then
  f="${pages_arg#@}"; [ -f "$f" ] || fail "sitemap not found: $f"
  while IFS= read -r line; do line="$(echo "$line"|tr -d '\r'|sed 's/#.*//'|xargs)"; [ -n "$line" ] && pages+=("$line"); done < "$f"
else IFS=',' read -r -a pages <<< "$pages_arg"; fi
[ "${#pages[@]}" -gt 0 ] || fail "no pages resolved from $pages_arg"

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
{ printf '['; first=1; for p in "${pages[@]}"; do
    pp="${p#/}"; pp="${pp%.html}"
    case "$pp" in sites/*) url="$JAHIA_HOST/$pp.html";; *) url="$JAHIA_HOST/sites/$site/$pp.html";; esac
    [ $first -eq 1 ] && first=0 || printf ','; printf '"%s"' "$url"
  done; printf ']'; } > "$work/pages.json"

# resolve / install axe + playwright (the skill installs them on demand)
node -e "require.resolve('@axe-core/playwright'); require.resolve('playwright')" >/dev/null 2>&1 || {
  for c in "$ROOT/node_modules" "/tmp/pw/node_modules"; do [ -d "$c/playwright" ] && export NODE_PATH="$c${NODE_PATH:+:$NODE_PATH}"; done
}
node -e "require.resolve('@axe-core/playwright'); require.resolve('playwright')" >/dev/null 2>&1 || {
  echo "installing @axe-core/playwright + playwright (one-time)…"
  (cd "$work" && npm install --no-save @axe-core/playwright playwright >/dev/null 2>&1 && npx playwright install chromium >/dev/null 2>&1)
  export NODE_PATH="$work/node_modules${NODE_PATH:+:$NODE_PATH}"
}
node -e "require.resolve('@axe-core/playwright')" >/dev/null 2>&1 || fail "could not resolve @axe-core/playwright (install: npm i -D @axe-core/playwright playwright && npx playwright install chromium)"

( cd "$work" && node "$SCRIPT" ); code=$?
[ "$code" -eq 0 ] || fail "site-review: a11y/SEO violations found (see report above)"
pass "site-review: all pages pass a11y (no critical/serious) + SEO baseline"
