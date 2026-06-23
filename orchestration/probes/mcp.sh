#!/usr/bin/env bash
# MCP availability probe: the Jahia MCP server is up and exposes tools.
# Usage: mcp.sh <project_path>
# Passes when GET <JAHIA_HOST>/modules/mcp returns >=1 tool. This is the
# server the content steps MUST prefer over GraphQL (see AGENTS.md section 7a).
# Optional: export JAHIA_MCP_TOKEN to send an APIToken Authorization header.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
load_env "${1:-}"
auth=()
[ -n "${JAHIA_MCP_TOKEN:-}" ] && auth=(-H "Authorization: APIToken ${JAHIA_MCP_TOKEN}")
# bash 3.2 (macOS default) errors on "${arr[@]}" for an empty array under set -u
out=$(curl -s ${auth[@]+"${auth[@]}"} "$JAHIA_HOST/modules/mcp" || true)
read -r ver n <<EOF
$(printf '%s' "$out" | python3 -c "import json,sys
try:
    d=json.load(sys.stdin); print(d.get('version','?'), len(d.get('tools',[])))
except Exception:
    print('? 0')")
EOF
echo "MCP $JAHIA_HOST/modules/mcp -> version $ver, $n tools"
[ "${n:-0}" -ge 1 ] || fail "Jahia MCP unavailable or 0 tools (GraphQL fallback permitted; note it in the run log)"
pass "Jahia MCP available ($n tools)"
