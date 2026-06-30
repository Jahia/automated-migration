#!/usr/bin/env bash
# content-fidelity.sh — gate that migrated CONTENT matches reality, not just structure.
# Other gates prove the site builds/renders; this catches the HOLLOW-site gaps a
# structure-only pass misses: empty listings, text-only (no images), blank shell, no EN,
# debris. See orchestration/probes/content-fidelity.py.
# Usage: content-fidelity.sh <project_path> <siteKey> [langs-csv]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
site="${2:?siteKey required}"
langs="${3:-fr,en}"
load_env "$proj"
python3 "$HERE/content-fidelity.py" "$site" "$proj" "$langs" || fail "content-fidelity: the migrated content is hollow vs the reference (see failures above)"
pass "content-fidelity: shell populated, images present, listings have content, EN present, no debris"
