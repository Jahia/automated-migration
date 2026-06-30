#!/usr/bin/env bash
# css-hooks.sh — FAITHFUL CSS class-hook gate (precise stripped-hook detector).
#
# The imported theme CSS styles the source's `.field-<name>` classes. A naive
# hardcoded-text fix can rename `className="field-x"` -> `"x"` to dodge the text
# gate — which strips the CSS hook and the value renders UNSTYLED ("CSS doesn't
# apply, pages look poor"). This catches exactly that regression, precisely:
#
#   flag a bare className token X when the theme CSS styles `.field-X` but NOT
#   `.X` standalone (so X has no styling unless it carries the field- prefix) AND
#   the view does not also render `field-X`.
#
# It deliberately does NOT require every source field to be a field-* class:
# views legitimately consolidate fields and use structural classes (`.content`,
# `.title-n2`) that the CSS also styles. Only a genuinely-orphaned value is a defect.
#
# Usage: css-hooks.sh <project_path> <namespace>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:-}"
[ -d "$proj/static/css" ] || { echo "  note: no static/css — skip"; pass "css-hooks: skipped (no theme CSS)"; }
[ -d "$proj/src/components" ] || fail "css-hooks: no src/components in $proj"

python3 - "$proj" <<'PY'
import re, glob, os, sys
proj = sys.argv[1]
css = " ".join(open(f, encoding='utf-8', errors='ignore').read() for f in glob.glob(f"{proj}/static/css/*.css"))
field_cls = set(re.findall(r'\.field-([a-zA-Z0-9_-]+)', css))          # .field-X styled
# bare classes the CSS styles standalone (structural) — collect class-selector tokens
bare_cls = set(re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]+)\b', css))
# a field hook is "field-only" if the CSS styles .field-X but NOT .X standalone
field_only = {x for x in field_cls if x not in bare_cls}
bad = []
for d in sorted(glob.glob(f"{proj}/src/components/*/")):
    for v in glob.glob(d + "*.server.tsx") + glob.glob(d + "*.client.tsx"):
        txt = open(v, encoding='utf-8', errors='ignore').read()
        present = set(re.findall(r'field-([a-zA-Z0-9_-]+)', txt))
        for m in re.finditer(r'className="([^"{]+)"', txt):
            for tok in m.group(1).split():
                if tok in field_only and tok not in present:
                    bad.append((os.path.basename(d.rstrip('/')), os.path.basename(v), tok))
# dedup
seen = set(); uniq = [b for b in bad if not (b in seen or seen.add(b))]
if uniq:
    print(f"Stripped CSS field-* hooks ({len(field_only)} field-only classes in the theme):")
    for comp, view, tok in uniq:
        print(f"  ✗ {comp}/{view}: className=\"...{tok}...\" → must be \"field-{tok}\" (theme styles .field-{tok}, not .{tok})")
    print(f"\nFAIL: {len(uniq)} value(s) render with a class the theme does not style — restore the field- "
          f"prefix and prop the value: <div className=\"field-{uniq[0][2]}\">{{props.x}}</div>.")
    sys.exit(1)
print(f"  · {len(field_only)} field-only CSS hooks; no view stripped a field- prefix off a styled value")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "css-hooks: a view stripped a field- CSS hook (value renders unstyled)"
pass "css-hooks: views keep the theme-CSS field-* hooks (no stripped, unstyled values)"
