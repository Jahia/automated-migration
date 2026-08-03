#!/usr/bin/env bash
# sxa-coverage.sh — Sitecore SXA analysis completeness gate.
#
# Sitecore SXA declares every component in the DOM (`.component <type>` +
# `.component-content` + `field-*`). This probe deterministically extracts EVERY
# component type from the cached source and FAILS if the analysis manifest doesn't
# ACCOUNT for each one — either mapped (a Jahia component's `sxaSource` lists it) or
# explicitly ignored (top-level `sxaIgnored` with a reason). This is what catches the
# silently-dropped components (top-bar, contact-block, key-figures…) that LLM
# "eyeball the page" discovery misses. Run during/after analysis.
#
# Usage: sxa-coverage.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ROOT="$(cd "$HERE/../.." && pwd)"
EXTRACT="$ROOT/orchestration/lib/sxa-extract.py"
cache="$proj/.reference/cache"
manifest="$proj/workflow-output/component-manifest.json"

[ -f "$EXTRACT" ] || fail "sxa-extract.py not found at $EXTRACT"
[ -d "$cache" ] || fail "no reference cache at $cache — run capture/analyze first"
[ -f "$manifest" ] || fail "no component-manifest.json at $manifest — run analyze first"

# 1. deterministic extraction
inv="$(python3 "$EXTRACT" "$cache" 2>/dev/null)"
echo "$inv" | python3 -c "import sys,json;d=json.load(sys.stdin);print('SXA source:',d['componentTypeCount'],'component types extracted')" || fail "extractor produced no JSON"

# 2. cross-check against the manifest's explicit accounting
python3 - "$manifest" <<PY
import sys, json, subprocess, os
inv = json.loads('''$inv''')
m = json.load(open(sys.argv[1]))
extracted = {c["type"] for c in inv["components"]}
# also accept aliases (e.g. top-bar / top-navbar) as the same source component
alias_of = {}
for c in inv["components"]:
    for a in c.get("aliases", []):
        alias_of[a] = c["type"]

mapped = set()
# crossCutting (chrome: header/nav/footer) types are MODELLED, just routed to an
# AbsoluteArea instead of a page area - scanning only the components list reported the
# source's header, nav and top-bar as unaccounted (2026-08-03).
for comp in (m.get("components", []) + m.get("crossCutting", [])):
    for s in comp.get("sxaSource", []):
        mapped.add(alias_of.get(s, s))
ignored = set(alias_of.get(s, s) for s in m.get("sxaIgnored", []))

# generic/structural SXA types that are template-level or pure layout — only count as
# "accounted" if the manifest explicitly lists them in sxaIgnored; otherwise flag them.
unmapped = sorted(extracted - mapped - ignored)
if unmapped:
    print(f"\nUNACCOUNTED SXA components ({len(unmapped)}) — neither mapped (a component's sxaSource) nor in sxaIgnored:")
    for t in unmapped:
        c = next(c for c in inv["components"] if c["type"] == t)
        print(f"  ✗ {t}  ({c['instances']} instances, fields: {', '.join(c['fields'][:5]) or '—'})")
    print("\nEvery SXA component must be either modelled (add it to a Jahia type and set")
    print('that type\\'s "sxaSource": ["<sxa-type>"]) or deliberately skipped (add it to a')
    print('top-level "sxaIgnored": ["<sxa-type>"] with a reason). No silent drops.')
    sys.exit(1)
print(f"\nall {len(extracted)} SXA component types accounted for ({len(mapped)} mapped, {len(ignored)} ignored)")
PY
code=$?
[ "$code" -eq 0 ] || fail "sxa-coverage: the manifest does not account for every source component (see above)"
pass "sxa-coverage: manifest accounts for every Sitecore SXA component in the source"
