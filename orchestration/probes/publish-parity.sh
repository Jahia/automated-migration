#!/usr/bin/env bash
# publish-parity.sh — reference + translation integrity, asserted in EDIT.
#
# EDIT-ONLY / NO-LIVE DOCTRINE (Julian, 2026-07-04: "aucun test en live"): the
# migration process is EDIT-only and LIVE is deliberately stale until Julian's
# single final publication (publish_site.sh). This probe therefore reads ONLY
# the EDIT workspace and NEVER publishes. It proves, entirely in EDIT:
#   1. every weakreference/reference on migrated content (image / logo /
#      j:linknode / j:defaultCategory / ...) resolves to a node that EXISTS
#      (its refNode is non-null) — a dangling ref is a broken asset regardless
#      of publication; the moment it publishes it renders as a hole;
#   2. TRANSLATION PARITY across the requested languages within EDIT — content
#      titled in one requested language must be titled in every requested
#      language (a missing translation node = a locale that publishes empty).
# The LIVE half of publish-COMPLETENESS ("EDIT actually reached LIVE") is
# verified AFTER the final publication by publish_site.sh + integrity.py
# --phase step_publish_final — NOT here (that would only re-measure stale LIVE).
#
# Usage:
#   publish-parity.sh <project_path> <siteKey> [langs_csv]
# e.g.
#   orchestration/probes/publish-parity.sh projects/supercar-garage supercar-garage en,fr
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
[ "$code" -eq 0 ] || fail "publish-parity: $site has dangling references or translation gaps in EDIT (see above)"
pass "publish-parity: $site — references resolve + translations parity in EDIT (LIVE completeness = post-publication)"
