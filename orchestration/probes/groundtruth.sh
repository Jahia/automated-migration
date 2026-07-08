#!/usr/bin/env bash
# groundtruth.sh — the P1 exit gate: the AUTHENTICATED EDIT-PREVIEW render of
# each Jahia page pixel-diffed against the certified source mirror (see
# lib/groundtruth_probe.mjs). EDIT-ONLY / NO-LIVE DOCTRINE (Julian, 2026-07-04:
# "aucun test en live"): the probe renders /cms/render/default/{lang}/… via
# Basic auth (Playwright httpCredentials) — the EDIT workspace Julian will
# publish — NEVER the anonymous LIVE page, and it never publishes. Render
# fidelity must reach the threshold on EVERY migrated page; semantic share is
# reported. Usage: groundtruth.sh <project> <siteKey> [threshold=99] [--pages a,b]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
project="${1:?project required (e.g. acquia-drupal)}"
site="${2:?siteKey required}"
thr="${3:-99}"
shift $(( $# >= 3 ? 3 : 2 )) || true
load_env "projects/$project"
require_node 20
# flush Jahia's output caches first — a stale cached render measuring 100 %
# against missing content is the worst possible false-positive (observed live)
HOST="${JAHIA_URL:-${JAHIA_HOST:-http://localhost:8080}}"; HOST="${HOST%/}"
UP="${JAHIA_USER:-root}"; [[ "$UP" == *:* ]] || UP="$UP:${JAHIA_PASS:-root}"
curl -sf -u "$UP" -H "Origin: $HOST" -X POST \
  "$HOST/modules/tools/cache.jsp" --data "action=flushOutputCaches" -o /dev/null \
  || echo "WARN: output-cache flush failed (tools cache.jsp) — results may be stale" >&2
# P3a: a --pages (subset) invocation writes review.partial.html, never the
# full-run review.html (orchestration/lib/groundtruth_probe.mjs) — point the
# failure message at whichever file THIS invocation actually wrote.
review_file="review.html"
for a in "$@"; do
  case "$a" in --pages) review_file="review.partial.html" ;; esac
done
node orchestration/lib/groundtruth_probe.mjs "projects/$project" "$site" "$thr" "$@" \
  || fail "ground-truth gate below ${thr}% (see projects/$project/workflow-output/groundtruth/${review_file})"
pass "ground truth >= ${thr}% on every migrated page"
