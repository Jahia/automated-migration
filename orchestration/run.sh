#!/usr/bin/env bash
# Submit a migration plan to the migration-orchestrator and start it.
#
# Usage:
#   bash orchestration/run.sh plans/sial-paris.plan.json [--start] [--watch]
#
#   (no flag)  create the run only, print the run_id
#   --start    create then immediately start the run
#   --watch    after starting, stream the SSE event log
#
# Env:
#   ORCH_URL   base URL of the orchestration loop (default http://localhost:8001)
set -euo pipefail

PLAN="${1:?usage: run.sh <plan.json> [--start] [--watch]}"
shift || true
ORCH_URL="${ORCH_URL:-http://localhost:8001}"
START=false; WATCH=false
for a in "$@"; do
  [ "$a" = "--start" ] && START=true
  [ "$a" = "--watch" ] && { START=true; WATCH=true; }
done

[ -f "$PLAN" ] || { echo "plan not found: $PLAN" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

# PLAN LINT before submission (2026-08-03): a plan with a relative repo_dir made the
# engine execute 0 commands and burn a whole run on "retries_exhausted" with no probe
# output at all. Also catches a referenced probe script that does not exist, a step
# that neither proves nor declares a gate, and broken depends_on. Cheap; refuse early.
python3 orchestration/probes/plan-lint.py "$PLAN" || {
  echo "run.sh: refusing to submit a plan that fails plan-lint" >&2; exit 2; }

echo "Submitting $PLAN to $ORCH_URL/runs ..."
RESP=$(curl -s -X POST "$ORCH_URL/runs" \
  -H "Content-Type: application/json" \
  --data-binary "@$PLAN")
RUN_ID=$(echo "$RESP" | jq -r '.run_id // empty')
[ -n "$RUN_ID" ] || { echo "failed to create run: $RESP" >&2; exit 1; }
echo "run_id = $RUN_ID  (status: $(echo "$RESP" | jq -r '.status'))"

if $START; then
  echo "Starting run $RUN_ID ..."
  curl -s -X POST "$ORCH_URL/runs/$RUN_ID/start" | jq -r '"status: " + .status'
fi

if $WATCH; then
  echo "Streaming events (Ctrl-C to stop; the run keeps going) ..."
  curl -sN "$ORCH_URL/runs/$RUN_ID/events"
fi

echo
echo "Run id: $RUN_ID"
echo "  start:  curl -X POST $ORCH_URL/runs/$RUN_ID/start"
echo "  watch:  curl -N $ORCH_URL/runs/$RUN_ID/events"
echo "  UI:     $ORCH_URL/app"
