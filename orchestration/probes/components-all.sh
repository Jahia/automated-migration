#!/usr/bin/env bash
# components-all.sh — PER-COMPONENT completeness gate (the #10 "fail at once" fix).
#
# The supercar fiasco: the loop implemented all components in one big step, the
# build passed, and 29/32 views were stubs / missing i18n. A module-wide
# build-only gate cannot see that. This probe instead loops EVERY component and
# validates each as its own unit, FAILING on the FIRST/ANY incomplete one and
# NAMING it — so a stubbed-or-half-done component is caught at the component, not
# hidden inside an aggregate "build succeeded".
#
# It deliberately runs only the CHEAP per-component checks in the loop:
#   1. source pairing  — a dir with a definition.cnd must also ship a *.server.tsx
#                        view (a type with no view never renders).
#   2. no-stub         — each view emits real JSX, no TODO/FIXME/not-implemented
#                        (same logic as no-stub.sh).
#   3. i18n            — every namespace type + property in the dir's CND has an
#                        en AND fr resource-bundle key (same check as
#                        component-validate.sh step 4 — catches the "shows raw
#                        sialp:topBar / iconClass technical names" bug).
# The EXPENSIVE module-wide work (yarn build) runs ONCE at the end, not per
# component. For the full per-component build→deploy→render chain used while
# iterating on a single component, use component-validate.sh.
#
# Usage: components-all.sh <project_path> <namespace>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
ns="${2:?namespace required (e.g. usg)}"
src="$proj/src"
[ -d "$src/components" ] || fail "no src/components in $proj"
load_env "$proj" 2>/dev/null || true

enp="$(find "$proj/settings/resources" -name "*_en.properties" 2>/dev/null | head -1)"
frp="$(find "$proj/settings/resources" -name "*_fr.properties" 2>/dev/null | head -1)"

# ── manifest coverage ─────────────────────────────────────────────────────────
# The per-component loop below only validates dirs that EXIST — it cannot see a
# component that was silently dropped (no dir created at all). That dropped-
# component path is exactly the "far from reality" failure. So first assert that
# every nodeType in the approved analysis manifest is actually declared in the
# module's CND. Names each missing one. (Skips quietly if no manifest.)
manifest="$proj/workflow-output/component-manifest.json"
if [ -f "$manifest" ]; then
  declared="$(grep -rhoE "\[${ns}:[a-zA-Z0-9]+\]" "$proj/src" "$proj/settings" 2>/dev/null | tr -d '[]' | sort -u)"
  want="$(python3 - "$manifest" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
want = set()
for c in m.get("components", []):
    nt = c.get("nodeType")
    if nt: want.add(nt)
    ct = c.get("childType"); cts = list(c.get("childTypes") or [])
    if isinstance(ct, str): cts.append(ct)
    for t in cts:
        if isinstance(t, str) and ":" in t: want.add(t)
    for ch in (c.get("children") or []):
        if isinstance(ch, dict) and ch.get("nodeType"): want.add(ch["nodeType"])
for t in sorted(want): print(t)
PY
)"
  missing="$(comm -23 <(printf '%s\n' "$want" | sort -u) <(printf '%s\n' "$declared" | sort -u) || true)"
  if [ -n "$missing" ]; then
    echo "Manifest components with NO CND type declared (silently dropped):" >&2
    printf '  ✗ %s\n' $missing >&2
    fail "components-all: $(printf '%s\n' "$missing" | grep -c .) approved manifest component(s) are missing from the module — implement them (CND + view), do not drop them"
  fi
  echo "  · manifest coverage: every approved component type is declared in the CND"
fi

# component dir = any directory under src/components that holds a view or a CND
# (bash 3.2 on macOS has no `mapfile` — use the read-loop idiom the other probes use)
dirs=()
while IFS= read -r d; do dirs+=("$d"); done < <(
  find "$src/components" -type f \( -name '*.server.tsx' -o -name 'definition.cnd' \) \
    -exec dirname {} \; 2>/dev/null | sort -u)
[ "${#dirs[@]}" -gt 0 ] || fail "no component dirs (no *.server.tsx / definition.cnd under $src/components)"

bad=()      # "Dir — reason" lines
checked=0
for d in "${dirs[@]}"; do
  rel="${d#$proj/}"
  cnd="$(find "$d" -maxdepth 1 -name 'definition.cnd' | head -1)"
  view="$(find "$d" -maxdepth 1 -name '*.server.tsx' | head -1)"
  checked=$((checked+1))
  reasons=()

  # ── 1. source pairing ──────────────────────────────────────────────────────
  if [ -n "$cnd" ] && [ -z "$view" ]; then
    reasons+=("has definition.cnd but NO *.server.tsx view (type never renders)")
  fi

  # ── 2. stub check (same heuristic as no-stub.sh) ────────────────────────────
  while IFS= read -r f; do
    grep -q "jahiaComponent" "$f" || continue
    tags=$(grep -oE '<[A-Za-z][A-Za-z0-9.]*' "$f" | wc -l | tr -d ' ')
    marker=$(grep -ciE '\b(TODO|FIXME)\b|not implemented|coming soon' "$f")
    if [ "$marker" -gt 0 ]; then reasons+=("$(basename "$f"): TODO/FIXME/not-implemented marker")
    elif [ "$tags" -eq 0 ]; then reasons+=("$(basename "$f"): emits no JSX (stub never filled)")
    fi
  done < <(find "$d" -maxdepth 1 -name '*.server.tsx' 2>/dev/null)

  # ── 3. i18n completeness for this dir's CND types/properties ────────────────
  if [ -n "$cnd" ]; then
    if [ -z "$enp" ] || [ -z "$frp" ]; then
      reasons+=("CND present but no _en/_fr .properties under $proj/settings/resources")
    else
      miss="$(python3 - "$cnd" "$ns" "$enp" "$frp" <<'PY'
import sys, re
cnd, ns, enp, frp = sys.argv[1:5]
en = open(enp, encoding="utf-8", errors="ignore").read()
fr = open(frp, encoding="utf-8", errors="ignore").read()
def key(s): return s.replace(":", r"\:")
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
        # Exempt fields Jahia labels itself (same set cnd-review exempts):
        #  - jcr:* / j:* — system/injected, Jahia provides the label (incl.
        #    j:linkType choices via linkTypeInitializer, j:subNodesView, j:linknode)
        #  - startNode / excludeNodes — query-root plumbing on listing components
        if prop.startswith("jcr:") or prop.startswith("j:") or prop in ("startNode", "excludeNodes"):
            continue
        k = f"{cur}.{key(prop)}"
        for blob, lab in ((en, "en"), (fr, "fr")):
            if not re.search(rf'\b{re.escape(k)}\s*=', blob):
                missing.append(f"[{lab}] {cur}.{prop}")
print("; ".join(missing))
PY
)"
      [ -n "$miss" ] && reasons+=("missing i18n keys: $miss")
    fi
  fi

  if [ "${#reasons[@]}" -gt 0 ]; then
    for r in "${reasons[@]}"; do bad+=("$rel — $r"); done
  fi
done

if [ "${#bad[@]}" -gt 0 ]; then
  echo "Incomplete components ($checked checked):"
  printf '  ✗ %s\n' "${bad[@]}"
  fail "components-all: ${#bad[@]} per-component issue(s) across $checked components — fix each named component (no module ships with a stubbed/unlabelled component)"
fi
echo "  $checked components: source paired, no stubs, i18n complete"

# ── module-wide build ONCE (not per component) ─────────────────────────────────
if [ -x "$HERE/build.sh" ]; then
  "$HERE/build.sh" "$proj" || fail "components-all: per-component checks passed but the module build failed (see above)"
else
  ( cd "$proj" && yarn build >/tmp/components-all-build.log 2>&1 ) || { tail -25 /tmp/components-all-build.log; fail "components-all: yarn build failed"; }
  echo "  build clean"
fi
pass "components-all: all $checked components complete (source + view + no-stub + i18n) and the module builds"
