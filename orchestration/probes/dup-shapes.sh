#!/usr/bin/env bash
# dup-shapes.sh — REUSE / VIEWS gate.
#
# A Jahia content type is defined by its DATA, not its markup. Two types with the
# SAME property shape are a modelling smell: they should be ONE type rendered by
# different VIEWS. This probe parses every CND type in the module, computes its
# sorted property signature (declared `- name` props, excluding j:/jcr: system
# props), and FAILS when two types share the same non-trivial signature.
#
# Usage: dup-shapes.sh <project_path> [namespace]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:-}"
[ -d "$proj/src" ] || fail "no src/ in $proj"

python3 - "$proj/src" "$ns" <<'PY'
import sys, re, os, glob
src, ns = sys.argv[1], sys.argv[2]
types = {}          # ns:type -> sorted tuple of prop names
cur = None
for f in glob.glob(os.path.join(src, "**", "*.cnd"), recursive=True):
    for raw in open(f, encoding="utf-8", errors="ignore"):
        line = raw.rstrip("\n")
        m = re.match(r"\s*\[([a-zA-Z0-9_]+:[a-zA-Z0-9_]+)\]", line)
        if m:
            cur = m.group(1); types.setdefault(cur, [])
            continue
        if cur is None: continue
        p = re.match(r"\s*-\s*([A-Za-z][A-Za-z0-9_]*)\s*\(", line)   # a property (not + child node)
        if p:
            name = p.group(1)
            if name.startswith(("j:", "jcr:")): continue            # skip system props
            types[cur].append(name)

# only consider this module's namespace when given
items = {t: tuple(sorted(set(props))) for t, props in types.items()
         if (not ns or t.startswith(ns + ":")) and props}

from collections import defaultdict
bysig = defaultdict(list)
for t, sig in items.items():
    if len(sig) >= 2:                # ignore trivial 0/1-field types (containers etc.)
        bysig[sig].append(t)

dups = {sig: ts for sig, ts in bysig.items() if len(ts) > 1}
if dups:
    print("Types sharing an identical property shape — make ONE type + views, not many:")
    for sig, ts in dups.items():
        print(f"  shape ({', '.join(sig)}):")
        for t in ts: print(f"      - {t}")
    sys.exit(1)
print(f"dup-shapes: {len(items)} {ns or ''} type(s) checked, no duplicate property shapes")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "dup-shapes: duplicate property shapes — consolidate into one type with additional views (Jahia reuse rule, AGENTS §2b)"
pass "dup-shapes: every type has a distinct property shape (no view-able duplicates)"
