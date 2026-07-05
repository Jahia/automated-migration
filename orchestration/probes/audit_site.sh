#!/usr/bin/env bash
# audit_site.sh — THE mandatory post-load verdict (observability plan B,
# Julian 2026-07-05: "un plan pour fixer l'observabilité pour que tu mesures
# réellement").
#
# One runner, three gates, in order:
#   1. G1/G5  contribution.py  — static, judges the content-load (coverage
#              floors, 0 dead props / empty shells / phantom markers; G5
#              media/link wiring with the vacuous-pass guard)
#   2. Ground truth groundtruth.sh — EVERY page, pixel, authenticated EDIT
#              preview vs the frozen source mirror (never LIVE — EDIT-only
#              doctrine). Produces workflow-output/groundtruth/review.html
#              with per-page side-by-side screenshots: the artifact a HUMAN
#              reviews. A low score is never waived here — waivers are
#              Julian's, with the diff image in front of him.
#   3. G6     editor-surface.py — forms.editForm exposes every wired prop rw
#              + every item has a Page Builder edit frame.
#
# NO load path may report "done" without this exiting 0. History: three
# rebuilds were reported "faithful" on home-made metrics while G1 was at 0.0%
# and 55/58 pages failed the pixel bar — the gates existed and were not run.
#
# Usage: audit_site.sh <project> <siteKey> [threshold=99]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
project="${1:?project required}"
site="${2:?siteKey required}"
thr="${3:-99}"
fails=()

echo "===== AUDIT $project / $site ====="
echo "== [1/3] G1/G5 contribution (static) =="
python3 "$HERE/contribution.py" "$project" || fails+=("G1/G5")

echo
echo "== [2/3] Ground truth (EVERY page, pixel >= ${thr}%, EDIT preview) =="
bash "$HERE/groundtruth.sh" "$project" "$site" "$thr" || fails+=("ground-truth")

echo
echo "== [3/3] G6 editor surface (forms + edit frames) =="
python3 "$HERE/editor-surface.py" "$project" "$site" || fails+=("G6")

echo
if [ "${#fails[@]}" -gt 0 ]; then
  echo "AUDIT: FAIL — red gates: ${fails[*]}"
  echo "  review: projects/$project/workflow-output/groundtruth/review.html"
  exit 1
fi
echo "AUDIT: PASS — G1/G5 + ground truth (all pages) + G6 green"
