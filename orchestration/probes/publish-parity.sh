#!/usr/bin/env bash
# publish-parity.sh — PUBLISH-COMPLETENESS gate.
#
# "Published" must mean "visible on live", not "the publish mutation returned
# true". This probe proves it by checking, in the LIVE workspace, that:
#   1. every weakreference on published content (image / logo / j:linknode /
#      j:defaultCategory / ...) resolves to a node that EXISTS in LIVE — catching
#      the recurring failure where a page was published but its DAM image /
#      linked node / category was not (reference → null → asset never renders);
#   2. every jmix:mainResource node with a translation in EDIT for a language
#      also has that translation in LIVE — catching content published WITHOUT
#      `languages:[...]` so the translation never reached live.
#
# Usage:
#   publish-parity.sh <project_path> <siteKey> [langs_csv]
# e.g.
#   orchestration/probes/publish-parity.sh projects/supercar-garage supercar-garage fr
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

proj="${1:?project_path required}"
site="${2:?siteKey required}"
langs="${3:-}"
load_env "$proj"

out="$(python3 "$HERE/publish-parity.py" "$site" "$langs" 2>&1)"
code=$?
echo "$out"
[ "$code" -eq 0 ] || fail "publish-parity: $site has unpublished referenced assets or missing translations in LIVE (see above)"
pass "publish-parity: $site — references + translations all present in LIVE"
