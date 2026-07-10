#!/usr/bin/env bash
# component-one.sh — completeness gate for ONE component (per-component story).
#
# The generated build plans decompose "implement components" into one story per
# manifest component (the anti-batch fix: a single mega-step stubbed 29/32 views).
# This probe validates exactly ONE component so its story is self-contained:
#
#   1. locate    — find the component dir by NODETYPE (grep of definition.cnd —
#                  no fragile name derivation)
#   2. pairing   — the dir ships at least one *.server.tsx view
#   3. no-stub   — views emit real JSX, no TODO/FIXME/not-implemented markers
#   4. i18n      — the type + every own CND property has en AND fr resource keys
#   5. cm view   — a cm.server.tsx registered as name:"cm" (jContent preview)
#
# Cheap by design (no build/deploy) — the module-wide build runs once in the
# components gate story (components-all.sh). Same checks as components-all.sh's
# per-dir loop, scoped to one dir and FAILING with the component named.
#
# Usage: component-one.sh <project_path> <namespace> <ns:nodeType | DirName>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:?namespace required}"
comp="${3:?nodeType (ns:type) or component dir name required}"
src="$proj/src"
[ -d "$src/components" ] || fail "no src/components in $proj"

# ── 1. locate the component dir ────────────────────────────────────────────────
if [[ "$comp" == *:* ]]; then
  # by nodeType: the dir whose definition.cnd declares [ns:type]
  cnd_hit="$(grep -rlE "^\[$(printf '%s' "$comp" | sed 's/[][\.*^$/]/\\&/g')\]" \
             "$src/components"/*/definition.cnd 2>/dev/null | head -1)"
  [ -n "$cnd_hit" ] || fail "component-one: no definition.cnd declares [$comp] under $src/components — component not implemented"
  d="$(dirname "$cnd_hit")"
else
  d="$src/components/$comp"
  [ -d "$d" ] || fail "component-one: no component dir $d"
fi
rel="${d#$proj/}"
cnd="$(find "$d" -maxdepth 1 -name 'definition.cnd' | head -1)"
echo "  · dir: $rel"

reasons=()

# ── 2. source pairing ──────────────────────────────────────────────────────────
view="$(find "$d" -maxdepth 1 -name '*.server.tsx' | head -1)"
if [ -n "$cnd" ] && [ -z "$view" ]; then
  reasons+=("has definition.cnd but NO *.server.tsx view (type never renders)")
fi

# ── 3. stub check ──────────────────────────────────────────────────────────────
while IFS= read -r f; do
  grep -q "jahiaComponent" "$f" || continue
  tags=$(grep -oE '<[A-Za-z][A-Za-z0-9.]*' "$f" | wc -l | tr -d ' ')
  marker=$(grep -ciE '\b(TODO|FIXME)\b|not implemented|coming soon' "$f")
  if [ "$marker" -gt 0 ]; then reasons+=("$(basename "$f"): TODO/FIXME/not-implemented marker")
  elif [ "$tags" -eq 0 ]; then reasons+=("$(basename "$f"): emits no JSX (stub never filled)")
  fi
done < <(find "$d" -maxdepth 1 -name '*.server.tsx' 2>/dev/null)

# ── 4. i18n completeness for this dir's CND types/properties ───────────────────
enp="$(find "$proj/settings/resources" -name "*_en.properties" 2>/dev/null | head -1)"
frp="$(find "$proj/settings/resources" -name "*_fr.properties" 2>/dev/null | head -1)"
if [ -n "$cnd" ]; then
  if [ -z "$enp" ] || [ -z "$frp" ]; then
    reasons+=("CND present but no _en/_fr .properties under $proj/settings/resources")
  else
    miss="$(python3 - "$cnd" "$ns" "$enp" "$frp" <<'PY'
import sys, re
cnd, ns, enp, frp = sys.argv[1:5]
en = open(enp, encoding="utf-8", errors="ignore").read()
fr = open(frp, encoding="utf-8", errors="ignore").read()
missing, cur = [], None
for line in open(cnd, encoding="utf-8", errors="ignore"):
    s = line.strip()
    mt = re.match(r"\[([\w]+):([\w]+)\]", s)
    if mt and mt.group(1).startswith(ns):
        cur = f"{mt.group(1)}_{mt.group(2)}"
        for blob, lab in ((en, "en"), (fr, "fr")):
            if not re.search(rf'\b{re.escape(cur)}\s*=', blob):
                missing.append(f"[{lab}] type label {cur}")
        continue
    if mt:
        cur = None
        continue
    mp = re.match(r"-\s*([\w:]+)\s*\(", s)
    if mp and cur:
        prop = mp.group(1)
        # system/injected props Jahia labels itself
        if prop.startswith("jcr:") or prop.startswith("j:") or prop in ("startNode", "excludeNodes"):
            continue
        k = f"{cur}.{prop.replace(':', chr(92)+':')}"
        for blob, lab in ((en, "en"), (fr, "fr")):
            if not re.search(rf'\b{re.escape(k)}\s*=', blob):
                missing.append(f"[{lab}] {cur}.{prop}")
print("; ".join(missing))
PY
)"
    [ -n "$miss" ] && reasons+=("missing i18n keys: $miss")
  fi
fi

# ── 5. cm (jContent preview) view ──────────────────────────────────────────────
if [ -n "$view" ] && [ -n "$cnd" ] && grep -qE '^\[[a-zA-Z]+:[a-zA-Z0-9]+\][[:space:]]*>' "$cnd"; then
  cmv="$(find "$d" -maxdepth 1 -name 'cm.server.tsx' | head -1)"
  if [ -z "$cmv" ]; then
    reasons+=("no cm.server.tsx (jContent preview) — run: python3 orchestration/lib/scaffold_cm_views.py $proj")
  elif ! grep -q 'name:[[:space:]]*"cm"' "$cmv"; then
    reasons+=("cm.server.tsx present but not registered as name:\"cm\"")
  fi
fi

if [ "${#reasons[@]}" -gt 0 ]; then
  echo "Incomplete component $rel:"
  printf '  ✗ %s\n' "${reasons[@]}"
  fail "component-one: $rel has ${#reasons[@]} issue(s) — fix this component before its story completes"
fi
pass "component-one: $rel complete (source + view + no-stub + i18n + cm)"
