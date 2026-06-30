#!/usr/bin/env bash
# mcp.sh — MCP-MANDATORY gate.
#
# All content writes MUST go through the Jahia MCP server's purpose-built tools.
# Hand-written GraphQL mutations are guesses that can corrupt the JCR (wrong shapes,
# missing mixins, i18n write bugs). This probe FAILS (no GraphQL fallback) unless
# the MCP server is up AND exposes the write tools the content load depends on:
#   content.create / content.update / content.translate / publication.publish / page.create
# The content step runs the deterministic MCP loader, so the API it needs must be present.
#
# Usage: mcp.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
load_env "${1:-}"
auth=()
[ -n "${JAHIA_MCP_TOKEN:-}" ] && auth=(-H "Authorization: APIToken ${JAHIA_MCP_TOKEN}")
# bash 3.2 (macOS default) errors on "${arr[@]}" for an empty array under set -u
out=$(curl -s --max-time 20 ${auth[@]+"${auth[@]}"} "$JAHIA_HOST/modules/mcp" || true)

printf '%s' "$out" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('FAIL: Jahia MCP not reachable / not JSON at $JAHIA_HOST/modules/mcp'); sys.exit(1)
tools = d.get('tools', [])
names = set(t if isinstance(t, str) else t.get('name') for t in tools)
required = {'content.create', 'content.update', 'content.translate', 'publication.publish', 'page.create'}
missing = sorted(required - names)
print(f'MCP version {d.get(\"version\",\"?\")}, {len(names)} tools')
if missing:
    print('MISSING required write tools:', ', '.join(missing))
    print('FAIL: MCP cannot do the content writes — do NOT fall back to guessed GraphQL '
          'mutations (JCR-corruption risk). Fix/upgrade the MCP module.')
    sys.exit(1)
print('  . required write tools present:', ', '.join(sorted(required)))
" || fail "mcp: required MCP write tools unavailable (GraphQL write fallback is forbidden)"
pass "mcp: Jahia MCP mandatory write tools present (content writes go through MCP, never guessed GraphQL)"
