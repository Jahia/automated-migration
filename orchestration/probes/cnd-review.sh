#!/usr/bin/env bash
# cnd-review.sh — deterministic CND-quality gate (from @jahia/agentic).
#
# Runs the agentic `check-cnd.mjs` linter over the module's CND files and FAILS
# on any antipattern, with file:line citations. Complements cnd-patterns.sh
# (which enforces our migration-specific rules); this brings the upstream
# Jahia CND best-practice checks.
#
# Usage: cnd-review.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
require_node 18

ROOT="$(cd "$HERE/../.." && pwd)"
SCRIPT="$ROOT/.agents/skills/dev/jahia-dev-review-cnd/scripts/check-cnd.mjs"
[ -f "$SCRIPT" ] || fail "check-cnd.mjs not found — run .agents/agentic-sync.sh to pull the agentic skills"

node "$SCRIPT" "$proj/src" || fail "cnd-review: CND antipatterns found (fix per check-cnd output above)"
pass "cnd-review: all CND files pass the agentic best-practice checks"
