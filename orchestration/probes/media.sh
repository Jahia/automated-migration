#!/usr/bin/env bash
# media.sh — MEDIA-TO-DAM gate (source-agnostic).
#
# extract.sh produced the deterministic image manifest (orchestration/images/
# <project>.json). This step imports every image into the DAM and verifies it
# landed. Without this the site ships text-only (the "0 of 40 images" failure).
#
# It runs the existing importer (images/import.py -> jahia-image-proxy servlet)
# and FAILS unless the import covered the manifest:
#   * <project>.imported.json exists and maps home images to real jcrPaths
#   * import success rate is high enough (a few WAF/404 misses tolerated)
# Wiring imported nodes onto content is verified separately by content-fidelity
# (image weakrefs SET).
#
# Usage: media.sh <project_path> <site_key>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
site="${2:?site_key required}"
project="$(basename "$proj")"
root="$(cd "$HERE/../.." && pwd)"
cd "$root"
load_env "$proj" 2>/dev/null || true

man="orchestration/images/$project.json"
[ -f "$man" ] || fail "media: no manifest $man — run extract.sh first (deterministic media extraction)"

echo "── importing manifest images into the DAM (jahia-image-proxy):"
python3 orchestration/images/import.py "$project" 2>&1 | tail -6 || true

imp="orchestration/images/$project.imported.json"
[ -f "$imp" ] || fail "media: import produced no $imp — the image-proxy import failed (check JAHIA_HOST / module deployed)"

python3 - "$man" "$imp" <<'PY'
import json, sys
man = json.load(open(sys.argv[1]))
imp = json.load(open(sys.argv[2]))
want = man.get("pages", {})
home_want = len(want.get("home", []))
home_ok = sum(1 for x in imp.get("home", []) if x.get("jcrPath"))
total_want = sum(len(v) for v in want.values())
total_ok = sum(1 for v in imp.values() for x in v if x.get("jcrPath"))
print(f"  · imported {total_ok}/{total_want} images ({home_ok}/{home_want} on home)")
fails = []
if home_want and home_ok == 0:
    fails.append(f"home: 0/{home_want} images imported to DAM — nothing landed (proxy/source unreachable)")
if total_want and total_ok < 0.6 * total_want:
    fails.append(f"only {total_ok}/{total_want} images imported (<60%) — import largely failed")
if fails:
    print("\nMEDIA FAILURES:")
    for f in fails: print("  ✗", f)
    sys.exit(1)
PY
rc=$?
[ "$rc" -eq 0 ] || fail "media: DAM import incomplete (see above)"
pass "media: manifest images imported into the DAM (content-fidelity verifies they are wired onto content)"
