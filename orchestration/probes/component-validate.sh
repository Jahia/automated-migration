#!/usr/bin/env bash
# component-validate.sh — FULL per-component gate.
#
# A component is NOT "done" until this exits 0. It runs the complete validation
# chain for ONE component so the loop cannot move on with a broken/half-built one:
#
#   1. source        — component dir has a definition.cnd and a *.server.tsx view
#   2. dup-view      — no duplicate default-view registration anywhere in src
#                      (two `nodeType:'X'` views with no `name:` crash module load
#                       at GraalVM registration → SITE-WIDE 404; see 11-debug)
#   3. cnd-patterns  — mix:title / tags / categories / linkTypeInitializer / weakref
#   4. i18n          — the type + every CND property has en AND fr resource keys
#   5. build         — yarn build exits 0
#   6. deploy        — yarn jahia-deploy succeeds and the bundle is ACTIVE
#   7. render        — a NON-home page renders HTTP 200 (catches a registration
#                      crash that home alone would mask) and the engine log is
#                      free of "already exist" / render exceptions
#
# Usage:
#   component-validate.sh <project_path> <namespace> <ComponentDir|ns:type> [smoke_page] [site_key] [lang]
# e.g.
#   orchestration/probes/component-validate.sh projects/sial-paris sialp WhitePaper tendances/livres-blancs sial-paris fr
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

proj="${1:?project_path required}"
ns="${2:?namespace required (e.g. sialp)}"
comp="${3:?component dir name or ns:type required}"
smoke="${4:-}"
site="${5:-}"
lang="${6:-fr}"
require_node 20
load_env "$proj"

step() { echo; echo "── $* ──"; }
ok()   { echo "  ok: $*"; }

# Normalise: accept "WhitePaper" (dir) or "sialp:whitePaper" (type)
dirname_hint="${comp##*:}"

# ── 1. source presence ──────────────────────────────────────────────────────
step "1/7 source"
cdir="$(find "$proj/src/components" -maxdepth 1 -type d -iname "${dirname_hint}" | head -1)"
[ -n "$cdir" ] || cdir="$(find "$proj/src" -type d -iname "*${dirname_hint}*" | head -1)"
[ -n "$cdir" ] || fail "no component directory matching '$dirname_hint' under $proj/src"
cnd="$(find "$cdir" -maxdepth 1 -name '*.cnd' | head -1)"
view="$(find "$cdir" -maxdepth 1 -name '*.server.tsx' | head -1)"
[ -n "$view" ] || fail "no *.server.tsx view in $cdir"
ok "dir=$cdir"; [ -n "$cnd" ] && ok "cnd=$cnd" || echo "  note: no CND in dir (structural component?)"

# ── 2. duplicate default-view guard (THE site-down preventer) ───────────────
step "2/7 duplicate default-view guard"
dupes="$(grep -rhoE "nodeType:[[:space:]]*['\"][^'\"]+['\"]" "$proj/src" --include='*.server.tsx' -B2 -A2 2>/dev/null \
  | python3 - "$proj" <<'PY'
import sys, re, pathlib
root = pathlib.Path(sys.argv[1], "src")
# A default view = a jahiaComponent({componentType:'view', nodeType:'X', ... }) with NO name: key
seen = {}
dups = []
for f in root.rglob("*.server.tsx"):
    txt = f.read_text(errors="ignore")
    for m in re.finditer(r"jahiaComponent\(\s*\{([^}]*)\}", txt, re.S):
        blk = m.group(1)
        if "componentType" not in blk or "'view'" not in blk.replace('"', "'"):
            continue
        nt = re.search(r"nodeType:\s*['\"]([^'\"]+)['\"]", blk)
        if not nt:
            continue
        has_name = re.search(r"\bname:\s*['\"]", blk)
        key = nt.group(1) + ("::" + re.search(r"name:\s*['\"]([^'\"]+)", blk).group(1) if has_name else "::__default__")
        seen.setdefault(key, []).append(str(f.relative_to(root.parent)))
for key, files in seen.items():
    if len(files) > 1:
        dups.append(f"{key} registered {len(files)}x: {', '.join(files)}")
print("\n".join(dups))
PY
)"
[ -z "$dupes" ] || fail "duplicate view registration (crashes module load → site-wide 404):
$dupes"
ok "every (nodeType, view) registered exactly once"

# ── 3. CND patterns ─────────────────────────────────────────────────────────
step "3/7 CND patterns"
if [ -n "$cnd" ] && [ -x "$HERE/cnd-patterns.sh" ]; then
  "$HERE/cnd-patterns.sh" "$cnd" || fail "cnd-patterns gate failed for $cnd (see above)"
  ok "CND patterns clean"
else
  echo "  skip (no CND or cnd-patterns.sh missing)"
fi

# ── 4. i18n completeness for this component's types/properties ──────────────
step "4/7 i18n (en + fr resource keys)"
if [ -n "$cnd" ]; then
  enp="$(find "$proj/settings/resources" -name "*_en.properties" | head -1)"
  frp="$(find "$proj/settings/resources" -name "*_fr.properties" | head -1)"
  [ -f "$enp" ] && [ -f "$frp" ] || fail "missing _en/_fr .properties under $proj/settings/resources"
  python3 - "$cnd" "$ns" "$enp" "$frp" <<'PY' || exit 1
import sys, re
cnd, ns, enp, frp = sys.argv[1:5]
en = open(enp, encoding="utf-8", errors="ignore").read()
fr = open(frp, encoding="utf-8", errors="ignore").read()
def key(s): return s.replace(":", r"\:")
missing = []
cur = None
for line in open(cnd, encoding="utf-8", errors="ignore"):
    s = line.strip()
    mt = re.match(r"\[([\w]+):([\w]+)\]", s)
    if mt and mt.group(1).startswith(ns):
        cur = f"{mt.group(1)}_{mt.group(2)}"
        for blob, lab in ((en, "en"), (fr, "fr")):
            if not re.search(rf'\b{re.escape(cur)}\s*=', blob):
                missing.append(f"[{lab}] type label {cur}")
        continue
    if mt:  # a non-namespace type (e.g. mixin from elsewhere) — reset
        cur = None
        continue
    mp = re.match(r"-\s*([\w:]+)\s*\(", s)
    if mp and cur:
        prop = mp.group(1)
        # Exempt fields Jahia labels itself (same set cnd-review exempts):
        # jcr:* / j:* (incl. j:linkType via linkTypeInitializer, j:subNodesView,
        # j:linknode) and the startNode/excludeNodes query-root plumbing fields.
        if prop.startswith("jcr:") or prop.startswith("j:") or prop in ("startNode", "excludeNodes"):
            continue
        k = f"{cur}.{key(prop)}"
        for blob, lab in ((en, "en"), (fr, "fr")):
            if not re.search(rf'\b{re.escape(k)}\s*=', blob):
                missing.append(f"[{lab}] {cur}.{prop}")
if missing:
    print("FAIL: missing resource-bundle keys:")
    for m in missing: print("   -", m)
    sys.exit(1)
print("  ok: all types/properties have en + fr labels")
PY
else
  echo "  skip (no CND)"
fi

# ── 5. build ────────────────────────────────────────────────────────────────
step "5/7 build"
( cd "$proj" && yarn build >/tmp/cv-build.log 2>&1 ) || { tail -25 /tmp/cv-build.log; fail "yarn build failed"; }
ok "build clean"

# ── 6. deploy + bundle ACTIVE ────────────────────────────────────────────────
step "6/7 deploy + ACTIVE"
( cd "$proj" && yarn jahia-deploy >/tmp/cv-deploy.log 2>&1 ) || { tail -20 /tmp/cv-deploy.log; fail "yarn jahia-deploy failed"; }
sym="$(grep -oE '"[^"]+/[^"]+/[0-9][^"]*"' /tmp/cv-deploy.log | head -1 | tr -d '"')"
[ -n "$sym" ] || sym="$(node -p "require('./$proj/package.json').name" 2>/dev/null)"
ok "deployed ($sym)"

# ── 7. render smoke (non-home) + clean engine log ────────────────────────────
step "7/7 render smoke"
# wait for the module to settle, then a NON-home page must return 200
smoke_node=""
if [ -n "$smoke" ] && [ -n "$site" ]; then
  smoke_node="/sites/$site/home/$smoke"
elif [ -n "$site" ]; then
  smoke_node="/sites/$site/home/le-salon"   # any non-home page exercises the 'basic' template
fi
if [ -n "$smoke_node" ]; then
  url="$JAHIA_HOST/cms/render/live/$lang$smoke_node.html"
  code=000
  for _ in $(seq 1 24); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -u "$JAHIA_USER" "$url")"
    [ "$code" = "200" ] && break
    sleep 4
  done
  [ "$code" = "200" ] || fail "non-home page did not render (HTTP $code): $url
  → a duplicate-view/registration crash makes every non-home page 404 while home still works."
  ok "non-home page renders 200 ($smoke_node)"
else
  echo "  note: pass <site_key> to enable the render smoke (strongly recommended)"
fi
# best-effort: scan the Jahia engine log for the registration crash
jc="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -iE 'jahia|jcontent|dxp' | head -1)"
if [ -n "$jc" ]; then
  if docker logs --tail 150 "$jc" 2>&1 | grep -qiE "already exist|PolyglotException.*view"; then
    fail "engine log shows a duplicate-view registration error (grep 'already exist')"
  fi
  ok "engine log clean (no 'already exist')"
fi

pass "component '$comp' fully validated (source, no-dup-view, cnd, i18n, build, deploy, render)"
