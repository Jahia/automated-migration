#!/usr/bin/env bash
# no-graphql-writes.sh — forbid GUESSED GraphQL content mutations (JCR-corruption guard).
#
# Content writes go through the Jahia MCP tools only. A hand-written GraphQL mutation
# (createNode / addChild / mutateProperty.setValue / setPropertiesBatch / deleteNode /
# publishNode ...) is a guess that can corrupt the JCR with wrong shapes or missing
# mixins. This scans committed scripts + run artifacts for GraphQL CONTENT MUTATIONS
# and FAILS if any are found. (GraphQL READ queries are fine — only mutations corrupt.)
#
# Usage: no-graphql-writes.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
root="$(cd "$HERE/../.." && pwd)"

# Scan CODE only (scripts) — never content/data JSON or docs, where the French word
# "mutation" legitimately appears in article text. Match GraphQL mutation SYNTAX:
# a `mutation` keyword followed by an optional name then `{` or `(`, or the JCR
# write API (mutateNode/mutateProperty/setPropertiesBatch/publishNode/deleteNode).
# Scope: this migration's ACTIVE write code — the project + the shared write path
# (orchestration/lib: mcp_client + loader + rewirer). The content load/rewire goes
# through MCP (lib/mcp_client.py), so guessed GraphQL must not appear here.
# Legacy GraphQL scripts (orchestration/images/set_*_refs.py, orchestration/news|focus)
# predate the MCP path; they are reported as a WARNING below (cleanup), not a blocker.
code_files="$(find "$proj" "$root/orchestration/lib" "$root/orchestration/probes" \
    \( -name '*.sh' -o -name '*.py' -o -name '*.mjs' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' \) \
    2>/dev/null | grep -vE '/(node_modules|\.git|dist|target|\.reference|__pycache__)/' \
    | grep -vE 'no-graphql-writes\.sh$')"
# Real GraphQL mutations are `mutation{...}` / `mutation Name {...}` (a brace) — never
# the prose word "mutations (". Require \bmutation + optional name + `{`, or the JCR
# write API called with `(`.
hits=""
[ -n "$code_files" ] && hits="$(echo "$code_files" | tr '\n' '\0' | xargs -0 grep -InE \
  '\bmutation([[:space:]]+[A-Za-z_][A-Za-z0-9_]*)?[[:space:]]*\{|\b(mutateNode|mutateProperty|setPropertiesBatch|publishNode|deleteNode)[[:space:]]*\(' \
  2>/dev/null | grep -vE 'content-fidelity|publish-parity' | head -20 || true)"

if [ -n "$hits" ]; then
  echo "Guessed GraphQL content mutations found (writes must use the Jahia MCP tools):" >&2
  printf '%s\n' "$hits" | sed "s#$root/##" | sed 's/^/  ✗ /' >&2
  fail "no-graphql-writes: $(printf '%s\n' "$hits" | grep -c .) GraphQL mutation site(s) — replace with MCP content.create/update/translate + publication.publish (via lib/mcp_client.py). Guessed mutations corrupt the JCR."
fi
# legacy cleanup WARNING (non-blocking): superseded GraphQL rewiring scripts
legacy="$(grep -lInE 'mutateNode|mutateProperty|setPropertiesBatch' \
  "$root/orchestration/images"/*.py 2>/dev/null || true)"
[ -n "$legacy" ] && { echo "  note: legacy GraphQL rewiring to migrate to MCP (lib/mcp_client.py):" >&2
  printf '%s\n' "$legacy" | sed "s#$root/##" | sed 's/^/    ~ /' >&2; }
pass "no-graphql-writes: active write path (project + lib/probes) is MCP-only (no guessed GraphQL mutations)"
