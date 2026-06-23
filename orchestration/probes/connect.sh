#!/usr/bin/env bash
# Gate 0 probe: Jahia server reachable and credentials valid.
# Usage: connect.sh <project_path>
# Passes when the GraphQL endpoint returns HTTP 200 or 400 (400 = reachable,
# no query sent). Fails on 000 (no server), 401 (bad creds), 403 (no perms).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
load_env "${1:-}"
code=$(curl -s -o /dev/null -w "%{http_code}" \
  -u "$JAHIA_USER" -H "Origin: $JAHIA_HOST" \
  "$JAHIA_HOST/modules/graphql" || true)
echo "graphql $JAHIA_HOST -> HTTP $code (user ${JAHIA_USER%%:*})"
[ "$code" = "200" ] || [ "$code" = "400" ] || fail "endpoint returned $code"
pass "Jahia reachable"
