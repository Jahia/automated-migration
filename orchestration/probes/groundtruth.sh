#!/usr/bin/env bash
# groundtruth.sh — the P1 exit gate: DEPLOYED Jahia pages pixel-diffed against
# the certified source mirror (see lib/groundtruth_probe.mjs). Render fidelity
# must reach the threshold on EVERY migrated page; semantic share is reported.
# Usage: groundtruth.sh <project> <siteKey> [threshold=99] [--pages a,b]
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
node orchestration/lib/groundtruth_probe.mjs "projects/$project" "$site" "$thr" "$@" \
  || fail "ground-truth gate below ${thr}% (see projects/$project/workflow-output/groundtruth/review.html)"
pass "ground truth >= ${thr}% on every migrated page"
