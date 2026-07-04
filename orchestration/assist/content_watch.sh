#!/usr/bin/env bash
# content_watch.sh <project> <site> [interval_s=120]
#
# Read-only observability ticker for step_content_load (Julian, 2026-07-04):
# runs the integrity belt (Jahia GraphQL reality vs artifact-derived expectations)
# on a fixed cadence and appends one JSONL tick to
#   projects/<project>/workflow-output/content-progress.jsonl
# Engine-independent: pure observer, safe to run mid-step. Consumed by the
# assistant heartbeat and (next engine restart) the cockpit progress endpoint.
set -u
proj="${1:?project}"; site="${2:?site}"; interval="${3:-120}"
cd "$(dirname "$0")/../.."
source .env.local
pp="projects/$proj"
out="$pp/workflow-output/content-progress.jsonl"
while true; do
  python3 orchestration/probes/integrity.py "$pp" "$site" --phase step_content_load >/dev/null 2>&1
  python3 - "$pp" "$out" <<'PY'
import json, sys, os
pp, out = sys.argv[1], sys.argv[2]
r = json.load(open(os.path.join(pp, "workflow-output", "integrity-report.json")))
pages = r["sections"]["instances"]["pages"]
exp = sum(p["expected"] for p in pages.values())
got = sum((p.get("actual_EDIT") or 0) for p in pages.values())
started = sum(1 for p in pages.values() if (p.get("actual_EDIT") or 0) > 0)
dam = os.path.join("orchestration", "images", "%s.dam.json" % r["project"])
media = 0
if os.path.isfile(dam):
    try:
        media = sum(1 for v in json.load(open(dam)).values() if v)
    except Exception:
        pass
tick = {"ts": r["ranAt"], "expected": exp, "created": got,
        "pct": round(100.0 * got / exp, 1) if exp else None,
        "pagesStarted": started, "pagesTotal": len(pages), "media": media}
with open(out, "a") as f:
    f.write(json.dumps(tick) + "\n")
print(json.dumps(tick), flush=True)
PY
  sleep "$interval"
done
