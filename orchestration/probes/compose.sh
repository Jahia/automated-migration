#!/usr/bin/env bash
# compose.sh — the COMPOSE GATE (pre-Jahia qualitative gate, ASSIST-PLAN).
#
# BEFORE anything is deployed to Jahia, prove the EXTRACTED content
# (orchestration/content/<project>.content-load.json) re-composes each page
# EXACTLY as the Jahia LIVE views will (skeletonRender.ts composeNode semantics:
# {{f:*}}/{{media:N}}/{{link:*}}/{{child:N}} splicing in document/creation order),
# then judge that composition byte-for-byte against the scoped local-mirror page
# it was extracted from. Fully offline — reads the content-load + local mirror,
# no Jahia, no network. Writes a human-reviewable side-by-side at
# <project>/workflow-output/compose/compose-review.html.
#
# Byte-exactness is the FROZEN bar (rule 23) — no threshold. Vision-adapter pages
# are whole-body byte-composable and judged; semantic-adapter pages are reported
# not-applicable (their fidelity is the ground-truth gate's job), never faked
# green and never falsely RED. Exit code IS the gate.
#
# Usage:
#   compose.sh <project_path> [--pages slug,slug]
# e.g.
#   orchestration/probes/compose.sh projects/discoverasr
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

proj="${1:?project_path required (e.g. projects/discoverasr)}"
shift || true

python3 "$HERE/../lib/compose_probe.py" "$proj" "$@" \
  || fail "compose gate: a composable page does NOT re-compose byte-identically to its scoped mirror (or no composable evidence) — see the divergence pointer above and the side-by-side review.html"
pass "compose gate: every composable page re-composes byte-identically to the scoped local mirror"
