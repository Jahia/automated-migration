#!/usr/bin/env bash
# session_start_check.sh — SessionStart hook payload (Julian's standing directive,
# 2026-07-04): if a migration-orchestrator run is active on 127.0.0.1:8011, inject
# context telling the assistant to arm the 5-minute reporting stack unprompted.
# Silent no-op when the engine is down or no run is active.
r=$(curl -s -m 2 http://127.0.0.1:8011/runs 2>/dev/null) || exit 0
printf '%s' "$r" | python3 -c '
import json, sys
try:
    runs = json.load(sys.stdin)
except Exception:
    sys.exit(0)
act = [x for x in runs if x.get("status") in ("running", "halted", "decision_pending", "paused")]
if not act:
    sys.exit(0)
ids = ", ".join("%s(%s)" % (x["run_id"], x["status"]) for x in act)
ctx = (
    "Active migration-orchestrator run(s) on 127.0.0.1:8011: " + ids + ". "
    "STANDING DIRECTIVE (Julian, 2026-07-04): without being asked, immediately arm the "
    "observability stack and report progress to Julian every 5 minutes: "
    "(1) background: orchestration/assist/monitor.sh <run_id> http://127.0.0.1:8011 "
    "(instant decision/gate/terminal detection); "
    "(2) background during content phases: orchestration/assist/content_watch.sh "
    "<project> <site> 120 (integrity-belt JSONL ticks); "
    "(3) background self-re-arming 5-min heartbeat: sleep 300 then print last belt "
    "ticks + run status; on wake, report to Julian with delta/rate/ETA and re-arm. "
    "Reports must state real Jahia-derived numbers (belt ticks), not just step status."
)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                         "additionalContext": ctx}}))
' 2>/dev/null
exit 0
