#!/usr/bin/env bash
# render-truth.sh — OBSERVABLE-RENDER gate.
#
# The agent must not claim a page "renders correctly" from a passing build or a
# grep/element count. This probe PROVES it by loading the page in a headless
# browser, scrolling through it, and FAILING on the render-only defects that
# slipped past count-based checks during real migrations:
#   - broken images (naturalWidth == 0) in the content
#   - content stuck hidden (opacity ~0 / 0-height) after a full scroll
#     → imported theme scroll-reveal (`:not(.slide-in){opacity:0}`) with no JS
#   - collapsed shared regions (header/nav/footer present but ~0 height)
#     → e.g. a fixed #header that breaks the sticky layout
#   - video sections with no <iframe>/<video> player
#     → YouTube rendered as <video><source type="video/youtube"> (never plays)
#   - (warning) dark-on-dark / low-contrast text in the header and cards
#
# A screenshot artifact is written next to the run so the result is inspectable.
#
# Usage:
#   render-truth.sh <url> [--edit] [screenshot_path]
# e.g.
#   orchestration/probes/render-truth.sh \
#     http://localhost:8080/sites/supercar-garage/home/actualites.html
#   # edit-frame variant (reveal-all expected, regions must render):
#   orchestration/probes/render-truth.sh \
#     "http://localhost:8080/cms/editframe/default/fr/sites/supercar-garage/home.html" --edit
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

url="${1:?page URL required}"
load_env ""
edit_flag=""
shot=""
shift || true
for a in "$@"; do
  case "$a" in
    --edit) edit_flag="--edit" ;;
    *) shot="$a" ;;
  esac
done

require_node 20

# Resolve Playwright: prefer a repo/global install, fall back to the known
# scratch install used during dev. Fail with actionable guidance if absent.
resolve_pw() {
  local candidates=(
    "$HERE/node_modules"
    "$(cd "$HERE/../.." && pwd)/node_modules"
    "/tmp/pw/node_modules"
    "$HOME/.cache/ms-playwright-node_modules"
  )
  if node -e "require.resolve('playwright')" >/dev/null 2>&1; then echo ""; return 0; fi
  for c in "${candidates[@]}"; do
    if [ -d "$c/playwright" ]; then echo "$c"; return 0; fi
  done
  return 1
}
PW_PATH="$(resolve_pw)" || fail "Playwright not found. Install it for the orchestration env: (cd orchestration && npm i playwright && npx playwright install chromium)"
[ -n "$PW_PATH" ] && export NODE_PATH="$PW_PATH${NODE_PATH:+:$NODE_PATH}"

# default screenshot artifact
if [ -z "$shot" ]; then
  mkdir -p "$HERE/../artifacts" 2>/dev/null || true
  slug="$(echo "$url" | sed 's#https\?://##; s#[^A-Za-z0-9]#_#g' | cut -c1-80)"
  shot="$HERE/../artifacts/render-truth_${slug}.png"
fi

# Raw-HTML error scan (runs BEFORE the visual check): Jahia renders query / module
# / JCR errors into the markup, sometimes inside HTML COMMENTS — invisible to a
# DOM/visual check, yet proof the page is broken. The agent flagged exactly this
# ("error visible in HTML" for an unprefixed JCR-SQL2 type); this enforces it.
raw="$(curl -s --max-time 30 ${JAHIA_USER:+-u "$JAHIA_USER"} -H "Origin: $JAHIA_HOST" "$url" 2>/dev/null)"
if [ -n "$raw" ]; then
  errln="$(printf '%s' "$raw" | grep -ioE '(node type does not exist|invalidqueryexception|repositoryexception|pathnotfoundexception|itemnotfoundexception|javax\.jcr\.[A-Za-z]+exception|org\.jahia\.[A-Za-z.]*exception|error rendering [^<]{0,60})[^<]{0,90}' | head -3)"
  if [ -n "$errln" ]; then
    echo "render-truth: error markers in HTML for $url (invisible in DOM but the page is broken):"
    printf '  ✗ %s\n' "$errln"
    fail "render-truth: $url contains JCR/query/render error markers in the HTML — fix the underlying error (e.g. an unprefixed JCR-SQL2 node type like [newsArticle] → [lsp:newsArticle])"
  fi
fi

out="$(node "$HERE/render-truth.mjs" "$url" "$shot" $edit_flag 2>&1)"
code=$?
echo "$out"
echo "screenshot: $shot"
if [ "$code" -eq 0 ]; then
  pass "render-truth: $url renders clean (no broken images / hidden content / collapsed regions / playerless video)"
else
  fail "render-truth: $url has render defects (see findings above + screenshot $shot)"
fi
