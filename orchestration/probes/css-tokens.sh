#!/usr/bin/env bash
# CSS theming gate: imported CSS must be variabilized into a :root token layer,
# the site-theme mixin must exist, and Layout.tsx must wire both override paths
# (token defaults -> base CSS -> site-node inline :root override -> uploaded
# override stylesheet). This is what makes a whole-site re-theme possible without
# a code redeploy. See skills 03 + 08.
# Usage: css-tokens.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
cssdir="$proj/static/css"
tokens="$cssdir/theme-tokens.css"

[ -d "$cssdir" ] || fail "no $cssdir — run asset import (skill 03) first"

# 1. token layer exists with :root custom properties
[ -f "$tokens" ] || fail "missing $tokens — run: python3 orchestration/lib/tokenize-css.py --out $tokens $cssdir/*.css"
grep -q ':root' "$tokens" || fail "$tokens has no :root block"
nvars=$(grep -oE -- '--[A-Za-z0-9-]+\s*:' "$tokens" | sort -u | wc -l | tr -d ' ')
[ "${nvars:-0}" -ge 3 ] || fail "$tokens defines only ${nvars} tokens — CSS not tokenized"

# 2. the rest of the CSS actually consumes the tokens
usages=$(grep -rlE 'var\(--' "$cssdir" --include='*.css' 2>/dev/null | grep -v 'theme-tokens.css' | wc -l | tr -d ' ')
[ "${usages:-0}" -ge 1 ] || fail "no stylesheet uses var(--token) outside theme-tokens.css — tokenization did not rewrite usages"

# 3. site-theme mixin declared
defs="$proj/settings/definitions.cnd"
{ [ -f "$defs" ] && grep -qiE 'mix:siteTheme' "$defs"; } || fail "settings/definitions.cnd is missing the <ns>Mix:siteTheme site-theme mixin"

# 4. Layout wires the cascade: loads the token layer + both override paths
layout="$(find "$proj/src" -name 'Layout*.tsx' 2>/dev/null | head -1)"
[ -n "$layout" ] || fail "no Layout*.tsx under $proj/src"
grep -q 'theme-tokens.css' "$layout" || fail "Layout does not load static/css/theme-tokens.css (token defaults must load first)"
grep -q ':root{' "$layout" || grep -qE 'themePrimaryColor|--color-primary' "$layout" \
  || fail "Layout does not emit a site-node :root{} override (mixin theme props)"
grep -q 'themeOverrideCss' "$layout" || fail "Layout does not link the uploaded themeOverrideCss override stylesheet"

# advisory: residual hardcoded colors OUTSIDE the token layer (theme-tokens.css is meant to hold the literals)
raw=$(find "$cssdir" -name '*.css' ! -name 'theme-tokens.css' -exec grep -hoE '#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b' {} + 2>/dev/null \
      | wc -l | tr -d ' ')
[ "${raw:-0}" -gt 0 ] && echo "note: ${raw} raw hex literal(s) remain in static/css (vendor/unkeyed values are fine; re-run tokenize-css.py if these are brand colors)" >&2

pass "CSS tokenized (${nvars} :root tokens, ${usages} stylesheet(s) using var()); siteTheme mixin + Layout overrides wired"
