#!/usr/bin/env bash
# P5 assistant monitor (ASSIST-PLAN §8 D1).
# Polls the engine's compact status and emits ONE line per event the assistant should act on:
#   PHASE <key> <title>        — epic/phase transition (a few per run)
#   DECISION_NEEDED <type> <step> — active gate or pending decision → assistant wakes, exits
#   TERMINAL <status>          — run completed/failed/aborted → exits
#   ENGINE_UNREACHABLE         — engine stopped answering → exits
# Deliberately SILENT on step-level transitions: per ASSIST-PLAN §0 rule 6 the assistant is
# not woken during the batch phase; it polls /status manually when it wants detail.
# Usage: monitor.sh <run_id> [engine_url]
set -u
RID="${1:?usage: monitor.sh <run_id> [engine_url]}"
URL="${2:-http://127.0.0.1:8001}"
prev_phase=""
fails=0
while true; do
  s=$(curl -s -m 5 "$URL/runs/$RID/status" 2>/dev/null || true)
  if [ -z "$s" ]; then
    fails=$((fails+1))
    if [ "$fails" -ge 6 ]; then echo "ENGINE_UNREACHABLE $URL"; exit 1; fi
    sleep 5; continue
  fi
  fails=0
  line=$(printf '%s' "$s" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
g = d.get("gate") or {}
p = d.get("phase") or {}
c = d.get("current_step") or {}
print("|".join([
    str(d.get("status", "")),
    str(p.get("key", "")), str(p.get("title", "")),
    "1" if g.get("active") else "", str(g.get("type", "")), str(g.get("step_id", "")),
    str(c.get("id", "")),
]))' 2>/dev/null)
  [ -z "$line" ] && { sleep 10; continue; }
  IFS='|' read -r status phase_key phase_title gate_active gate_type gate_step step_id <<< "$line"
  if [ -n "$phase_key" ] && [ "$phase_key" != "$prev_phase" ]; then
    echo "PHASE $phase_key $phase_title"
    prev_phase="$phase_key"
  fi
  case "$status" in
    completed|failed|aborted) echo "TERMINAL $status (last step: $step_id)"; exit 0 ;;
  esac
  if [ -n "$gate_active" ]; then
    echo "DECISION_NEEDED type=$gate_type step=$gate_step"
    exit 0
  fi
  sleep 10
done
