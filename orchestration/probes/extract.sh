#!/usr/bin/env bash
# extract.sh — DETERMINISTIC EXTRACTION gate (source-agnostic).
#
# Migration is an ETL job: the captured DOM is the source of truth, and the bulk
# work (media + content) must be EXTRACTED from it, not improvised by the LLM.
# This runs the deterministic extractors and FAILS unless they produced complete
# manifests grounded in the real source:
#   * source_detect  — identify the CMS (picks the adapter; generic always works)
#   * extract_media  — orchestration/images/<project>.json: every captured image,
#                      per page (the manifest images/import.py consumes)
#   * extract_content— orchestration/content/<project>.content-data.json: the REAL
#                      per-page content (field values / blocks), not placeholders
#
# Gate: a manifest must exist, be non-trivial, and cover the home page. This is
# what makes media+content first-pass-complete instead of LLM-skipped.
#
# Usage: extract.sh <project_path> <site_key>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
site="${2:?site_key required}"
project="$(basename "$proj")"
root="$(cd "$HERE/../.." && pwd)"
cd "$root"

[ -d "$proj/.reference" ] || fail "extract: no $proj/.reference — capture the source first (capture-reference)"

echo "── source detection:"
python3 orchestration/lib/source_detect.py "$project" || fail "extract: source_detect failed"

echo "── media extraction:"
python3 orchestration/lib/extract_media.py "$project" "$site" || fail "extract: extract_media failed"

echo "── content extraction:"
python3 orchestration/lib/extract_content.py "$project" "$site" || fail "extract: extract_content failed"

# completeness checks on the produced manifests
python3 - "$project" <<'PY'
import json, sys
project = sys.argv[1]
fails = []
try:
    media = json.load(open(f"orchestration/images/{project}.json"))
except Exception as e:
    print(f"FAIL: media manifest unreadable: {e}"); sys.exit(1)
pages = media.get("pages", {})
total = sum(len(v) for v in pages.values())
if "home" not in pages or not pages["home"]:
    fails.append("media: home page has 0 images (extraction missed the main page)")
if total < 5:
    fails.append(f"media: only {total} images across all pages — extraction looks empty")
try:
    content = json.load(open(f"orchestration/content/{project}.content-data.json"))
except Exception as e:
    print(f"FAIL: content-data unreadable: {e}"); sys.exit(1)
cp = content.get("pages", {})
def units(v): return len(v.get("instances", v.get("blocks", [])))
if "home" not in cp or units(cp["home"]) == 0:
    fails.append("content: home page has 0 content units (extraction produced nothing real)")
realchars = sum(len(f) for v in cp.values() for i in v.get("instances", []) for f in i["fields"].values()) \
          + sum(len(b.get("text", "")) for v in cp.values() for b in v.get("blocks", []))
if realchars < 500:
    fails.append(f"content: only {realchars} chars of real text extracted — far too little")
if fails:
    print("\nEXTRACTION FAILURES:")
    for f in fails: print("  ✗", f)
    sys.exit(1)
print(f"\n  · media: {total} image refs across {len(pages)} pages (home={len(pages.get('home',[]))})")
print(f"  · content: adapter={content.get('adapter')}, {realchars} chars of real text across {len(cp)} pages")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "extract: manifests incomplete (see above) — extraction must be complete before build/content"
pass "extract: source detected, media + content deterministically extracted from the real source"
