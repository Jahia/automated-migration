#!/usr/bin/env bash
# invalidate.sh <project> <stage> [--dry-run]   (P4 observability remediation)
#
# Explicit stage invalidation: removes ONE pipeline stage's on-disk artifacts
# for a project, AND every stage downstream of it, so the next run is an
# HONEST regeneration instead of silently resuming on stale bytes. This is the
# manual, blunt-instrument complement to the TOOL_VERSION cache-busting consts
# added in crawl-site.py / segment_probe.mjs / load_content.py (P4 sibling
# change) — those catch an algorithm change automatically; this is for "I
# changed something upstream and want a clean slate from here down."
#
# Stage DAG (derived from orchestration/ANALYZE-PIPELINE.md + the real step
# order/deps encoded in orchestration/lib/gen_plan.py::build_plan, cross-checked
# against orchestration/plans/discoverasr-zone.plan.json for the newer zone arm
# — see the case blocks below for exactly which tool produces which stage):
#
#   crawl -> mirror -> semantic -> {segment | zone} -> model -> contentload
#          -> compose -> cnd -> reconstruct -> {load | dam} -> groundtruth
#
# `segment` (vision arm: segment_probe.mjs) and `zone` (fine-signal arm:
# zone_detect.py+zone_to_contentload.py) are ALTERNATE siblings at the same DAG
# position — invalidating one never wipes the other, but BOTH cascade into
# `model` and everything after (whichever arm actually ran, the downstream
# artifacts must go). Likewise `load` (the MCP load ledger) and `dam` (the DAM
# dedupe map) are siblings that both feed `groundtruth`.
#
# This script only manages the ANALYZE + local-content-prep portion of the
# pipeline (crawl..groundtruth) — never the module scaffold/deploy or
# site-creation steps: those write to the actual npm module source tree
# (projects/<p>/src, settings/, ...) and to LIVE Jahia, neither of which is a
# "cache" safe to blanket-rm. This script never touches Jahia at all.
#
# SAFETY:
#   - <project> must be a bare name: no "/" and no "..".
#   - <project> must be an existing directory under $PROJECTS_ROOT.
#   - every path this script can remove is re-validated (belt AND suspenders:
#     the per-stage lists below, THEN an allow-list check in remove_path, THEN
#     a by-name deny-list) to be anchored under that one project's
#     workflow-output/, or one of the two explicitly-named extras that live
#     outside it (the project's DAM dedupe map, the project's analyze-phase
#     content-load spec).
#   - NEVER removes manual-decisions.json, manual-decisions-backups/, or
#     zoning-config.json — these are Julian's hand-authored zoning decisions
#     and namespace/mode overrides (the manual zoning inspector's single
#     source of truth), not derived caches; the engine only ever READS them.
#     Same for scope-rules.json (reviewer-authored scope decisions from the
#     step_model_review / step_exceptions_review gates). Wiping any of these
#     is data loss, not cache invalidation — see the 2026-07-06 incident.
#   - --dry-run prints exactly what a real run would remove, without removing.
#
# Usage:
#   invalidate.sh <project> <stage> [--dry-run]
#   invalidate.sh -h                              # list stages + what each removes
#
# Env:
#   PROJECTS_ROOT   defaults to <repo_root>/projects. Override for testing so
#                   this NEVER has to touch a real project (see the self-test
#                   in the scratchpad, which points it at a throwaway tree).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PROJECTS_ROOT="${PROJECTS_ROOT:-$REPO/projects}"

ALL_STAGES="crawl mirror semantic segment zone model contentload compose cnd reconstruct load dam groundtruth"
NEVER_TOUCH="manual-decisions.json manual-decisions-backups zoning-config.json scope-rules.json adjudication"

usage() {
  cat <<'EOF'
invalidate.sh <project> <stage> [--dry-run]
invalidate.sh -h

Removes a pipeline stage's artifacts AND every downstream stage's artifacts
for one project, forcing an honest regeneration instead of a silent resume on
stale bytes. Prints every path it removes (or would remove, with --dry-run).

STAGES (in DAG order; "removes" lists what THIS stage alone deletes — running
it also deletes everything listed under every stage that follows it in the
chain shown for that stage):

  crawl        chain: crawl -> ALL
               removes: workflow-output/page-inventory.json
                        .reference/cache/            (crawl-site.py's HTML +
                                                       asset cache, incl. the
                                                       TOOL_VERSION marker)

  mirror       chain: mirror -> semantic..groundtruth
               removes: workflow-output/local-mirror/
                        workflow-output/local-mirror-prescope/
                                        (scope_apply.py's pre-scope snapshot —
                                         must go WITH local-mirror or the next
                                         scope-rules apply silently rebuilds
                                         from the STALE snapshot)
                        workflow-output/mirror/      (mirror_probe.mjs gate)

  semantic     chain: semantic -> segment,zone..groundtruth
               removes: workflow-output/semantic-candidates.json
                        workflow-output/semantic-templates.json
                        workflow-output/html-fragments/
                        workflow-output/scope-report.json

  segment      chain: segment -> model..groundtruth  (vision arm only; NOT zone)
               removes: workflow-output/segment/*    (segment_probe.mjs)
               EXCEPT segment/adjudication/ — human verdicts (B6), preserved
               like manual-decisions.json; delete by hand to redo them.

  zone         chain: zone -> model..groundtruth      (fine-signal arm only; NOT segment)
               removes: workflow-output/zone3-<project>.json
                        workflow-output/zone-xref.json
                        workflow-output/zone-overlay/
                        workflow-output/zone-review.html
                        workflow-output/component-model.json
                        workflow-output/component-model/
               NEVER removes manual-decisions.json / manual-decisions-backups/
               / zoning-config.json (see SAFETY above).

  model        chain: model -> contentload..groundtruth
               removes: workflow-output/component-manifest.json
                        workflow-output/promote-roles.json
                        workflow-output/passthrough-overrides.json
                        workflow-output/naming-proposals.json
                        workflow-output/grouping.json
                        workflow-output/grouping.manifest.json
                        workflow-output/orphans.json

  contentload  chain: contentload -> compose..groundtruth
               removes: orchestration/content/<project>.content-load.json
                                        (analyze-phase extraction spec — lives
                                         outside workflow-output by design)

  compose      chain: compose -> cnd..groundtruth
               removes: workflow-output/compose/     (compose_probe.py gate)

  cnd          chain: cnd -> reconstruct..groundtruth
               removes: workflow-output/definitions.cnd
                        workflow-output/views.json
               (never definitions.cnd.scaffold-orig — that is written by the
               MODULE-phase merge_cnd.py, out of this DAG's scope.)

  reconstruct  chain: reconstruct -> load,dam,groundtruth
               removes: workflow-output/reconstruct/ (reconstruct_probe.mjs fidelity gate)

  load         chain: load -> groundtruth            (NOT dam)
               removes: workflow-output/load-ledger.json
                        workflow-output/content-progress.jsonl
                        workflow-output/integrity-report.json
               NOTE: this deletes the LOCAL trace only — it never touches
               Jahia (forbidden). load_content.py's --clean reconcile can
               still "bootstrap" a page back to ALIGNED from EXISTING JCR
               structure alone when the ledger entry is simply absent; if you
               need a guaranteed full reload against unchanged JCR content,
               pair this with load_content.py --force-rebuild on the next run.

  dam          chain: dam -> groundtruth             (NOT load)
               removes: orchestration/images/<project>.dam.json

  groundtruth  chain: groundtruth
               removes: workflow-output/groundtruth/
                        workflow-output/groundtruth-masks.json

Env: PROJECTS_ROOT (default: <repo>/projects)
EOF
}

# ---- downstream closure: self + every stage that must also go, in order ----
downstream_stages() {
  case "$1" in
    crawl)       echo "crawl mirror semantic segment zone model contentload compose cnd reconstruct load dam groundtruth" ;;
    mirror)      echo "mirror semantic segment zone model contentload compose cnd reconstruct load dam groundtruth" ;;
    semantic)    echo "semantic segment zone model contentload compose cnd reconstruct load dam groundtruth" ;;
    segment)     echo "segment model contentload compose cnd reconstruct load dam groundtruth" ;;
    zone)        echo "zone model contentload compose cnd reconstruct load dam groundtruth" ;;
    model)       echo "model contentload compose cnd reconstruct load dam groundtruth" ;;
    contentload) echo "contentload compose cnd reconstruct load dam groundtruth" ;;
    compose)     echo "compose cnd reconstruct load dam groundtruth" ;;
    cnd)         echo "cnd reconstruct load dam groundtruth" ;;
    reconstruct) echo "reconstruct load dam groundtruth" ;;
    load)        echo "load groundtruth" ;;
    dam)         echo "dam groundtruth" ;;
    groundtruth) echo "groundtruth" ;;
    *)           return 1 ;;
  esac
}

# ---- one stage's OWN artifact paths (absolute), one per line ----
# $1 = stage, uses $PROJECT_DIR / $PROJECT / $REPO from the caller's scope.
stage_paths() {
  local pd="$PROJECT_DIR"
  case "$1" in
    crawl)
      echo "$pd/workflow-output/page-inventory.json"
      echo "$pd/.reference/cache"
      ;;
    mirror)
      echo "$pd/workflow-output/local-mirror"
      echo "$pd/workflow-output/local-mirror-prescope"
      echo "$pd/workflow-output/mirror"
      ;;
    semantic)
      echo "$pd/workflow-output/semantic-candidates.json"
      echo "$pd/workflow-output/semantic-templates.json"
      echo "$pd/workflow-output/html-fragments"
      echo "$pd/workflow-output/scope-report.json"
      ;;
    segment)
      # Enumerate children instead of the dir wholesale: segment/adjudication/
      # holds HUMAN verdicts (B6, adjudicate_ingest.mjs) — same class as
      # manual-decisions.json (decisions, not derived caches), so it is
      # preserved; delete it by hand if a redo of adjudicated pages is wanted.
      if [ -d "$pd/workflow-output/segment" ]; then
        for c in "$pd/workflow-output/segment"/* "$pd/workflow-output/segment"/.[!.]*; do
          [ -e "$c" ] || continue
          [ "$(basename -- "$c")" = "adjudication" ] && continue
          echo "$c"
        done
      fi
      ;;
    zone)
      echo "$pd/workflow-output/zone3-$PROJECT.json"
      echo "$pd/workflow-output/zone-xref.json"
      echo "$pd/workflow-output/zone-overlay"
      echo "$pd/workflow-output/zone-review.html"
      echo "$pd/workflow-output/component-model.json"
      echo "$pd/workflow-output/component-model"
      ;;
    model)
      echo "$pd/workflow-output/component-manifest.json"
      echo "$pd/workflow-output/promote-roles.json"
      echo "$pd/workflow-output/passthrough-overrides.json"
      echo "$pd/workflow-output/naming-proposals.json"
      echo "$pd/workflow-output/grouping.json"
      echo "$pd/workflow-output/grouping.manifest.json"
      echo "$pd/workflow-output/orphans.json"
      ;;
    contentload)
      echo "$REPO/orchestration/content/$PROJECT.content-load.json"
      ;;
    compose)
      echo "$pd/workflow-output/compose"
      ;;
    cnd)
      echo "$pd/workflow-output/definitions.cnd"
      echo "$pd/workflow-output/views.json"
      ;;
    reconstruct)
      echo "$pd/workflow-output/reconstruct"
      ;;
    load)
      echo "$pd/workflow-output/load-ledger.json"
      echo "$pd/workflow-output/content-progress.jsonl"
      echo "$pd/workflow-output/integrity-report.json"
      ;;
    dam)
      echo "$REPO/orchestration/images/$PROJECT.dam.json"
      ;;
    groundtruth)
      echo "$pd/workflow-output/groundtruth"
      echo "$pd/workflow-output/groundtruth-masks.json"
      ;;
    *)
      return 1
      ;;
  esac
}

# ---- remove one path, defense-in-depth ----
remove_path() {
  local p="$1" base
  base="$(basename -- "$p")"
  for nt in $NEVER_TOUCH; do
    if [ "$base" = "$nt" ]; then
      echo "invalidate.sh: REFUSING to touch protected user artifact: $p" >&2
      return 1
    fi
  done
  case "$p" in
    "$PROJECT_DIR/workflow-output/"*|"$PROJECT_DIR/.reference/cache")
      : ;;
    "$REPO/orchestration/content/$PROJECT.content-load.json"|"$REPO/orchestration/images/$PROJECT.dam.json")
      : ;;
    *)
      echo "invalidate.sh: REFUSING out-of-bounds path: $p" >&2
      return 1
      ;;
  esac
  if [ -e "$p" ]; then
    if [ "$DRY" = 1 ]; then
      echo "  [dry-run] would remove: $p"
    else
      rm -rf -- "$p"
      echo "  removed: $p"
    fi
  else
    echo "  (absent) $p"
  fi
}

# ---- args ----
DRY=0
POSITIONAL=()
for a in "$@"; do
  case "$a" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY=1 ;;
    *) POSITIONAL+=("$a") ;;
  esac
done

if [ "${#POSITIONAL[@]}" -lt 2 ]; then
  usage
  exit 2
fi
PROJECT="${POSITIONAL[0]}"
STAGE="${POSITIONAL[1]}"

case "$PROJECT" in
  */*|*..*|"")
    echo "invalidate.sh: invalid project name '$PROJECT' (bare name only, no / or ..)" >&2
    exit 2
    ;;
esac

PROJECT_DIR="$PROJECTS_ROOT/$PROJECT"
if [ ! -d "$PROJECT_DIR" ]; then
  echo "invalidate.sh: no such project directory: $PROJECT_DIR" >&2
  exit 2
fi

if ! STAGES_TO_WIPE="$(downstream_stages "$STAGE")"; then
  echo "invalidate.sh: unknown stage '$STAGE'" >&2
  echo "valid stages: $ALL_STAGES" >&2
  exit 2
fi

mode="live"; [ "$DRY" = 1 ] && mode="dry-run"
echo "invalidate.sh: project=$PROJECT stage=$STAGE mode=$mode"
echo "  chain: $STAGES_TO_WIPE"
for s in $STAGES_TO_WIPE; do
  echo "== stage: $s =="
  while IFS= read -r p; do
    remove_path "$p"
  done < <(stage_paths "$s")
done
