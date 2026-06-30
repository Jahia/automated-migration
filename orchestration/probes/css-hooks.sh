#!/usr/bin/env bash
# css-hooks.sh — FAITHFUL CSS class-hook gate.
#
# The imported theme CSS styles the source's `.field-<name>` classes (+ the
# .component/.component-content structure). If a migrated view drops a field-*
# class the CSS targets, that styling silently disappears — the "CSS doesn't apply,
# pages look poor" failure. (It is also what a naive hardcoded-text fix causes:
# renaming className="field-x" to "x" to dodge the text gate strips the CSS hook.)
#
# This enforces faithful transcription of the CSS contract: for each component, the
# view MUST carry every field-<name> class that is BOTH (a) used by the source for
# that type (content-data) AND (b) actually styled by the theme CSS (static/css).
# The correct pattern keeps the hook AND uses a prop: <div className="field-x">{prop}</div>.
#
# Usage: css-hooks.sh <project_path> <namespace>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:?namespace required}"
project="$(basename "$proj")"
root="$(cd "$HERE/../.." && pwd)"; cd "$root"

manifest="$proj/workflow-output/component-manifest.json"
content="orchestration/content/$project.content-data.json"
[ -f "$manifest" ] || { echo "  note: no manifest — skip css-hooks"; pass "css-hooks: skipped (no manifest)"; }
[ -f "$content" ]  || { echo "  note: no content-data — run extract first"; pass "css-hooks: skipped (no content-data)"; }

python3 - "$proj" "$content" "$manifest" <<'PY'
import json, re, glob, os, sys
proj, content_p, manifest_p = sys.argv[1], sys.argv[2], sys.argv[3]
m = json.load(open(manifest_p)); content = json.load(open(content_p))
# field-* names the theme CSS actually styles (bare, prefix stripped)
css_fields = set()
for f in glob.glob(f"{proj}/static/css/*.css"):
    for cls in re.findall(r'\.field-([a-zA-Z0-9_-]+)', open(f, encoding='utf-8', errors='ignore').read()):
        css_fields.add(cls)
# SXA type -> lsp type; source field names per lsp type
t2l = {}
for c in m.get("components", []):
    for s in (c.get("sxaSource") or []):
        t2l[s.lower()] = c["nodeType"]
lsp_fields = {}
for pg in content.get("pages", {}).values():
    for inst in pg.get("instances", []):
        lt = t2l.get(inst["type"].lower())
        if lt:
            lsp_fields.setdefault(lt, set()).update(inst.get("fields", {}).keys())
bad = []
for d in sorted(glob.glob(f"{proj}/src/components/*/")):
    vs = glob.glob(d + "*.server.tsx")
    if not vs:
        continue
    txt = " ".join(open(v, encoding='utf-8', errors='ignore').read() for v in vs)
    mt = re.search(r'nodeType:\s*"([^"]+)"', txt)
    lt = mt.group(1) if mt else None
    req = lsp_fields.get(lt, set()) & css_fields
    have = set(re.findall(r'field-([a-zA-Z0-9_-]+)', txt))
    missing = sorted(req - have)
    if missing:
        bad.append((os.path.basename(d.rstrip('/')), lt, missing))
if bad:
    print(f"Views missing theme-CSS field-* hooks ({len(css_fields)} field classes in the CSS):")
    for name, lt, miss in bad:
        print(f"  ✗ {name} ({lt}): add className=\"field-<x>\" for {miss}")
    print(f"\nFAIL: {len(bad)} component(s) drop CSS-styled field-* hooks — keep the source class and "
          f"put the value in a prop: <div className=\"field-x\">{{props.x}}</div>. Renaming the class "
          f"removes the theme styling (pages look unstyled).")
    sys.exit(1)
print(f"  · {len(css_fields)} CSS-styled field classes; every view carries the hooks its source fields need")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "css-hooks: views drop CSS-styled field-* hooks (theme styling lost)"
pass "css-hooks: views faithfully carry the theme-CSS field-* class hooks"
