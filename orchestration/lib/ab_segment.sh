#!/usr/bin/env bash
# ab_segment.sh <projects/name> [ns] — A/B information strategy (ASSIST-PLAN §4 B3).
#
# Runs the HEURISTIC arm (group_llm.py + assemble_manifest.py) on the same frozen
# mirror into a SEPARATE dir <PP>/workflow-output/ab/heuristic/ (never clobbers the
# real artifacts), gathers the VISION arm's existing segment-check.json + manifest
# metrics, and writes <PP>/workflow-output/segment/ab-report.json comparing the arms.
#
# HONESTY NOTE on fidelity: reconstruct_probe.mjs reads component-manifest.json from
# a HARDCODED path and uses it only for overlay LABELS — its pixel measurement is the
# in-browser heuristic identify(), independent of which arm produced the manifest.
# There is no CLI to point it at an alternate manifest/outdir, so a per-arm fidelity
# comparison is NOT feasible: the report compares structural metrics only and sets
# "fidelityCompared": false (never fake a judge).
#
# Exit 0 iff the report was written (an information strategy: heuristic-arm failure
# is recorded IN the report, it does not fail evidence gathering). Exit 1 on missing
# prerequisites.
set -uo pipefail

PP="${1:?usage: ab_segment.sh <projects/name> [ns]}"
CAND="$PP/workflow-output/semantic-candidates.json"
SEGCHECK="$PP/workflow-output/segment/segment-check.json"
VISION_MANIFEST="$PP/workflow-output/component-manifest.json"
AB_DIR="$PP/workflow-output/ab/heuristic"
REPORT="$PP/workflow-output/segment/ab-report.json"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -s "$CAND" ] || { echo "FAIL: $CAND not found (run semantic_extract first)" >&2; exit 1; }
mkdir -p "$AB_DIR" "$(dirname "$REPORT")"

# namespace: explicit arg > vision manifest's nodeType prefix > "ns"
NS="${2:-}"
if [ -z "$NS" ] && [ -s "$VISION_MANIFEST" ]; then
  NS="$(python3 -c "
import json,sys
try:
    m=json.load(open('$VISION_MANIFEST'))
    cs=(m.get('components') or [])+(m.get('crossCutting') or [])
    print(cs[0]['nodeType'].split(':')[0] if cs else '')
except Exception: print('')
")"
fi
NS="${NS:-ns}"

echo "[ab_segment] $PP — heuristic arm into $AB_DIR (ns=$NS)"

# ── heuristic arm (isolated outputs — group_llm's internal gate manifest also
#    lands in AB_DIR as grouping.manifest.json) ─────────────────────────────
GROUPING="$AB_DIR/grouping.json"
HEUR_MANIFEST="$AB_DIR/component-manifest.json"
GROUP_LOG="$AB_DIR/group_llm.log"
ASSEMBLE_LOG="$AB_DIR/assemble.log"

python3 "$HERE/group_llm.py" "$PP" --model deepseek-v4-flash --ns "$NS" \
  --out "$GROUPING" >"$GROUP_LOG" 2>&1
GROUP_RC=$?

ASSEMBLE_RC=""
if [ "$GROUP_RC" -eq 0 ] && [ -s "$GROUPING" ]; then
  python3 "$HERE/assemble_manifest.py" "$CAND" --group "$GROUPING" --ns "$NS" \
    --out "$HEUR_MANIFEST" >"$ASSEMBLE_LOG" 2>&1
  ASSEMBLE_RC=$?
fi

# ── compare arms + write the report (deterministic, no LLM) ────────────────
python3 - "$PP" "$NS" "$GROUP_RC" "${ASSEMBLE_RC:-}" <<'PY'
import json, os, sys

pp, ns, group_rc, assemble_rc = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
assemble_rc = int(assemble_rc) if assemble_rc != "" else None
wo = f"{pp}/workflow-output"

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

def manifest_metrics(man):
    if not man:
        return None
    comps = man.get("components") or []
    xcut = man.get("crossCutting") or []
    return {
        "components": len(comps),
        "crossCutting": len(xcut),
        "namingQuality": man.get("namingQuality"),
        "namingViolations": len(man.get("namingViolations") or []),
        "componentNames": sorted(c.get("nodeType") or c.get("name") or "?" for c in comps),
    }

# vision arm — existing artifacts (protocol v1 or v2 segment-check shapes)
segcheck = load(f"{wo}/segment/segment-check.json")
vision_pages = []
if segcheck:
    if segcheck.get("protocol") == "v2":
        for cl in segcheck.get("clusters") or []:
            for pg in cl.get("pages") or []:
                vision_pages.append({"slug": pg.get("slug"), "cluster": cl.get("id"),
                                     "agreement": pg.get("agreement"),
                                     "coverage": pg.get("coverage"),
                                     "pass": pg.get("pass"), "greenBy": pg.get("greenBy")})
        vision_gate = segcheck.get("gatePass")
    else:
        for pg in segcheck.get("pages") or []:
            vision_pages.append({"slug": pg.get("slug"),
                                 "agreement": pg.get("agreement"),
                                 "coverage": pg.get("coverage"),
                                 "pass": pg.get("gatePass"), "greenBy": None})
        vision_gate = bool(vision_pages) and all(p["pass"] for p in vision_pages)
else:
    vision_gate = None

vision = {
    "arm": "vision",
    "gatePass": vision_gate,
    "pages": vision_pages,
    "manifest": manifest_metrics(load(f"{wo}/component-manifest.json")),
    "artifacts": {"segmentCheck": f"{wo}/segment/segment-check.json",
                  "manifest": f"{wo}/component-manifest.json"},
}

# heuristic arm — this run's isolated artifacts
heur_manifest = load(f"{wo}/ab/heuristic/component-manifest.json")
heuristic = {
    "arm": "heuristic",
    "groupLlmExit": group_rc,
    "partitionPass": assemble_rc == 0 if assemble_rc is not None else False,
    "manifest": manifest_metrics(heur_manifest),
    "artifacts": {"grouping": f"{wo}/ab/heuristic/grouping.json",
                  "manifest": f"{wo}/ab/heuristic/component-manifest.json",
                  "logs": [f"{wo}/ab/heuristic/group_llm.log",
                           f"{wo}/ab/heuristic/assemble.log"]},
}

report = {
    "project": pp,
    "ns": ns,
    "vision": vision,
    "heuristic": heuristic,
    # reconstruct_probe.mjs measures fidelity with its own in-browser heuristic
    # identify() and reads the manifest from a hardcoded path for LABELS only —
    # no CLI exists to judge an alternate manifest, so no per-arm pixel fidelity.
    "fidelityCompared": False,
    "fidelityNote": ("reconstruct_probe.mjs has no --manifest/--outdir CLI and its "
                     "measurement is manifest-independent; structural metrics only."),
}
out = f"{wo}/segment/ab-report.json"
with open(out, "w") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
v = vision["manifest"] or {}
h = heuristic["manifest"] or {}
print(f"[ab_segment] {out}")
print(f"  vision:    gate={vision['gatePass']} components={v.get('components')} "
      f"naming={v.get('namingQuality')}")
print(f"  heuristic: partition={'PASS' if heuristic['partitionPass'] else 'FAIL'} "
      f"components={h.get('components')} naming={h.get('namingQuality')}")
PY
RC=$?
[ "$RC" -eq 0 ] && [ -s "$REPORT" ] || { echo "FAIL: ab-report.json not written" >&2; exit 1; }
exit 0
