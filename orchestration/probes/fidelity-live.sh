#!/usr/bin/env bash
# fidelity-live.sh — structural fidelity gate, JS-rendered both sides.
#
# Replaces the weak headings-only `fidelity.sh` (which used curl — static — and
# so passed pages that were visually wrong once JS ran). This renders the LOCAL
# Jahia page in headless Chromium (localhost, no WAF) and a REFERENCE the same
# way, then FAILS the local on: missing sections, listing/card shortfall, or
# missing facet values; warns on image shortfall / section reorder. Saves a
# reference-vs-local screenshot pair.
#
# The reference source avoids re-hitting the WAF'd origin: prefer the persisted
# browser capture `projects/<p>/.reference/captured/<slug>.html`; a URL also works
# for non-WAF sites or a pre-warmed page.
#
# Usage:
#   fidelity-live.sh <referenceSrc> <live_url>
# e.g.
#   fidelity-live.sh projects/supercar-garage/.reference/captured/actualites.html \
#     http://localhost:8080/sites/supercar-garage/home/actualites.html
#   fidelity-live.sh https://example.com/news http://localhost:8080/sites/acme/home/news.html
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
ref="${1:?reference source (captured .html file or URL) required}"
url="${2:?live page URL required}"
require_node 20

# resolve Playwright (same approach as render-truth.sh)
if ! node -e "require.resolve('playwright')" >/dev/null 2>&1; then
  for c in "$HERE/node_modules" "$(cd "$HERE/../.." && pwd)/node_modules" "/tmp/pw/node_modules"; do
    [ -d "$c/playwright" ] && export NODE_PATH="$c${NODE_PATH:+:$NODE_PATH}" && break
  done
fi
node -e "require.resolve('playwright')" >/dev/null 2>&1 || fail "Playwright not found (cd orchestration && npm i playwright && npx playwright install chromium)"

# a file reference must exist; absolutize it
case "$ref" in
  http://*|https://*) : ;;
  *) [ -f "$ref" ] || fail "reference file not found: $ref (capture it first via /capture-reference, or pass a URL)"; ref="$(cd "$(dirname "$ref")" && pwd)/$(basename "$ref")" ;;
esac

mkdir -p "$HERE/../artifacts" 2>/dev/null || true
out="$(node "$HERE/fidelity-live.mjs" "$ref" "$url" "$HERE/../artifacts" 2>&1)"; code=$?
echo "$out"
echo "screenshots: orchestration/artifacts/fidelity-ref.png + fidelity-local.png"
[ "$code" -eq 0 ] || fail "fidelity-live: $url is materially below the reference (see findings above)"
pass "fidelity-live: $url matches the reference (sections, listings, facets)"
