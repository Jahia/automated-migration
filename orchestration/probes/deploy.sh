#!/usr/bin/env bash
# Deploy probe: module builds and deploys to the running Jahia instance.
# Usage: deploy.sh <project_path>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"

# Guard: content-type icon trap. The JS engine maps settings/content-types-icons/
# into the bundle's /icons path automatically. Shipping a SECOND root icons/ folder
# (i.e. "icons" in package.json files[]) creates duplicate JAR entries -> the install
# fails with java.util.zip.ZipException. The provisioning API still returns success,
# so the deploy fails SILENTLY and the old bundle keeps running. Catch it before deploy.
if [ -d "$proj/settings/content-types-icons" ]; then
  pkg="$proj/package.json"
  if [ -f "$pkg" ]; then
    pj="const p=JSON.parse(require('fs').readFileSync('$pkg','utf8'));"
    if node -e "$pj const f=p.files||[]; process.exit(f.includes('icons')?1:0)"; then :; else
      fail "package.json files[] lists a root \"icons\" folder -> duplicate /icons entries cause a SILENT java.util.zip.ZipException on deploy. Remove it; icons live in settings/content-types-icons/ only."
    fi
    if ! node -e "$pj const s=(p.jahia||{})['static-resources']||''; process.exit(s.split(',').map(x=>x.trim()).includes('/icons')?0:1)"; then
      fail "package.json jahia.static-resources is missing /icons -> content-type icon URLs (/modules/<m>/icons/<type>.png) will 404 and editors see blank icons. Add /icons to static-resources."
    fi
  fi
fi

require_node 20
# The @jahia/vite-plugin jahia-deploy CLI reads JAHIA_USER as "user:password" and
# JAHIA_HOST as the base URL, via dotenv.config() which never OVERRIDES existing env.
# The engine injects .env.local into probe env (verifier.py), whose plain
# JAHIA_USER=root shadows the module's .env -> deploy authenticates as guest -> 401
# on /modules/api/provisioning (found live, M4 deploy attempt 1). Recompose the
# CLI's expected forms from the canonical vars so manual AND engine runs both work.
case "${JAHIA_USER:-}" in
  *:*) : ;;
  *) export JAHIA_USER="${JAHIA_USER:-root}:${JAHIA_PASS:?JAHIA_PASS required to compose jahia-deploy credentials}" ;;
esac
export JAHIA_HOST="${JAHIA_HOST:-${JAHIA_URL:?JAHIA_URL required}}"

# NEVER-SEEN-VERSION discipline (2026-07-23): Jahia skips re-registering type
# definitions for any module VERSION it ever processed — a changed CND deployed
# on a seen version silently keeps the OLD definitions (cost: 3 manual bumps in
# one day). Stamp the CND surface; on change, bump the minor version before
# deploying. Stamp updates only after a successful deploy.
cnd_hash=$(cat "$proj"/settings/definitions.cnd "$proj"/src/components/*/definition.cnd 2>/dev/null | shasum -a 256 | cut -d' ' -f1)
stamp="$proj/workflow-output/.cnd-deploy-stamp"
if [ -n "$cnd_hash" ] && [ "$(cat "$stamp" 2>/dev/null)" != "$cnd_hash" ] && [ -f "$stamp" ]; then
  node -e "
    const fs=require('fs'); const p='$proj/package.json';
    const pkg=JSON.parse(fs.readFileSync(p,'utf8'));
    const [ma,mi]=pkg.version.split('.').map(Number);
    pkg.version=[ma,mi+1,0].join('.');
    fs.writeFileSync(p,JSON.stringify(pkg,null,2));
    console.log('deploy.sh: CND changed -> version bumped to '+pkg.version+' (never-seen-version rule)');
  "
fi
( cd "$proj" && yarn build && yarn jahia-deploy )
[ -n "$cnd_hash" ] && printf '%s' "$cnd_hash" > "$stamp"

# rule 14: 'Operation successful' is NOT 'bundle started' — an unresolvable
# nodetype requirement (a view registered for an undeclared type) leaves the
# module INSTALLED but never ACTIVE, silently (observed live:
# scg:keyFiguresItem). Verify a module type actually exists; module start is
# async, so poll briefly.
HOST="${JAHIA_URL:-${JAHIA_HOST:-http://localhost:8080}}"; HOST="${HOST%/}"
UP="${JAHIA_USER:-root}"; [[ "$UP" == *:* ]] || UP="$UP:${JAHIA_PASS:-root}"
ns="$(grep -oE '^\[[a-zA-Z][a-zA-Z0-9]*:rawHtml\]' "$proj/settings/definitions.cnd" 2>/dev/null | head -1 | tr -d '[]' | cut -d: -f1)"
if [ -n "$ns" ] && grep -q "\[$ns:rawHtml\]" "$proj/settings/definitions.cnd" 2>/dev/null; then
  ok=""
  for _i in $(seq 1 45); do
    if curl -sf -u "$UP" -H "Origin: $HOST" -H 'Content-Type: application/json' \
        -X POST "$HOST/modules/graphql" \
        -d "{\"query\":\"{ jcr { nodeTypesByNames(names: [\\\"$ns:rawHtml\\\"]) { name } } }\"}" \
        2>/dev/null | grep -q "\"$ns:rawHtml\""; then ok=1; break; fi
    sleep 4
  done
  [ -n "$ok" ] || fail "module deployed but type $ns:rawHtml never appeared — bundle did NOT start (check Jahia logs for unresolved requirements)"
fi
pass "build + jahia-deploy succeeded for $proj${ns:+ (types live: $ns)}"
