#!/usr/bin/env bash
# edit-frame.sh — PAGE-BUILDER editability gate.
#
# A page can render perfectly on `live` yet be blank/uneditable in the Page
# Builder — the recurring case: a shared region (nav / footer / topbar) is an
# AbsoluteArea whose node has NO child content, so it renders nothing in the
# edit frame (works in live). This probe logs in, opens the Page Builder for a
# page, finds the editframe iframe, and FAILS if the header/nav/footer regions
# are blank or there are no editable area markers.
#
# Usage:
#   edit-frame.sh <project_path> <siteKey> <lang> [pagePath=home]
# e.g.
#   orchestration/probes/edit-frame.sh projects/supercar-garage supercar-garage fr home
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

proj="${1:?project_path required}"
site="${2:?siteKey required}"
lang="${3:?language required}"
pagePath="${4:-home}"
load_env "$proj"
require_node 20

# Playwright resolution (same approach as render-truth.sh)
if ! node -e "require.resolve('playwright')" >/dev/null 2>&1; then
  for c in "$HERE/node_modules" "$(cd "$HERE/../.." && pwd)/node_modules" "/tmp/pw/node_modules"; do
    [ -d "$c/playwright" ] && export NODE_PATH="$c${NODE_PATH:+:$NODE_PATH}" && break
  done
fi
node -e "require.resolve('playwright')" >/dev/null 2>&1 || fail "Playwright not found (cd orchestration && npm i playwright && npx playwright install chromium)"

user="${JAHIA_USER%%:*}"; pwd_="${JAHIA_USER#*:}"
out="$(node "$HERE/edit-frame.mjs" "$JAHIA_HOST" "$user" "$pwd_" "$site" "$lang" "$pagePath" 2>&1)"
code=$?
echo "$out"
[ "$code" -eq 0 ] || fail "edit-frame: $site/$pagePath has blank/uneditable shared regions in Page Builder (see above)"
pass "edit-frame: $site/$pagePath — shared regions render and are editable in Page Builder"
