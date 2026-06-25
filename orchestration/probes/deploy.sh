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
( cd "$proj" && yarn build && yarn jahia-deploy )
pass "build + jahia-deploy succeeded for $proj"
