#!/usr/bin/env bash
# pixel-calibrate.sh — measure the pixel-diff NOISE FLOOR and auto-set a fair threshold.
#
# "Pixel perfect" must be provable BEFORE an agent burns attempts on it: two fresh
# renders of the SAME reference page differ by some floor (font raster, AA, timing,
# late assets). The gate threshold has to sit above that floor or it is unpassable.
#
# Renders the project's reference home page twice (pixel-diff.mjs --calibrate),
# takes the diff%% as the floor, and writes into
# orchestration/content/<project>.pixel-config.json:
#   noiseFloorPct  — the measurement, for transparency
#   maxDiffPct     — raised to (floor + margin) if the configured value is below it
#                    (never lowered: a stricter configured bar is kept if achievable)
#
# Deterministic (task_type script in generated plans). Run once per project before
# the content phase; re-run if the reference bundle or pixel config changes.
#
# Usage: pixel-calibrate.sh <project_path> <site> [margin_pct]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

proj="${1:?project_path required}"
site="${2:?site required}"
margin="${3:-1.0}"
project="$(basename "$proj")"
cfg="orchestration/content/$project.pixel-config.json"

capdir="$proj/.reference/captured"
crawldir="$proj/.reference/cache/_crawl"

# reference for the home page (same resolution as pixel.sh)
ref=""
[ -f "$capdir/home.html" ] && ref="$capdir/home.html"
if [ -z "$ref" ] && [ -d "$crawldir" ]; then
  ref="$(find "$crawldir" -maxdepth 2 -name '*.html' 2>/dev/null | grep -E '/[a-z]{2}(-[A-Z]{2})?\.html$' | head -1)"
fi
[ -n "$ref" ] || fail "pixel-calibrate: no reference DOM for the home page (capture/crawl first)"

hide=""; ref_origin=""
if [ -f "$cfg" ]; then
  hide="$(python3 -c "import json;print('|'.join(json.load(open('$cfg')).get('hideSelectors',[])))")"
  ref_origin="$(python3 -c "import json;print(json.load(open('$cfg')).get('referenceOrigin',''))")"
fi
if [ -z "$ref_origin" ] && [ -d "$crawldir" ]; then
  host_dir="$(find "$crawldir" -mindepth 1 -maxdepth 1 -type d | head -1)"
  [ -n "$host_dir" ] && ref_origin="https://$(basename "$host_dir")"
fi

out="$proj/workflow-output/pixel/.calibration"
echo "── calibrating: two fresh renders of ${ref#$proj/}"
node "$HERE/pixel-diff.mjs" "$(cd "$(dirname "$ref")" && pwd)/$(basename "$ref")" "--calibrate" \
  "$out" "100" "$hide" "$ref_origin" >/tmp/pixel-cal-$$.json 2>/tmp/pixel-cal-$$.err \
  || { head -3 /tmp/pixel-cal-$$.err; fail "pixel-calibrate: calibration render failed"; }

floor="$(python3 -c "import json;print(json.load(open('/tmp/pixel-cal-$$.json'))['diffPct'])")"
rm -f /tmp/pixel-cal-$$.json /tmp/pixel-cal-$$.err

python3 - "$cfg" "$floor" "$margin" <<'PY'
import json, sys, os
cfg, floor, margin = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
d = json.load(open(cfg)) if os.path.exists(cfg) else {}
prev = float(d.get("maxDiffPct", 2.0))
recommended = round(floor + margin, 1)
d["noiseFloorPct"] = floor
if recommended > prev:
    d["maxDiffPct"] = recommended
    print(f"noise floor {floor}% > configured bar: maxDiffPct {prev} -> {recommended} (floor + {margin})")
else:
    print(f"noise floor {floor}%: configured maxDiffPct {prev} is achievable — kept")
json.dump(d, open(cfg, "w"), indent=2, ensure_ascii=False)
PY

pass "pixel-calibrate: noise floor ${floor}% recorded in $cfg"
