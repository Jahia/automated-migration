#!/usr/bin/env bash
# namespace-check.sh — scripted Jackrabbit namespace-conflict gate (rule 13).
#
# Namespace prefixes persist in Jackrabbit's registry across module uninstalls:
# deploying a module whose CND redeclares an existing prefix with a DIFFERENT
# URI (or whose URI is already bound to another prefix) fails at install time —
# or worse, silently corrupts type resolution. This is the mandatory pre-deploy
# check; it drives the Jahia tools Groovy console over HTTP (POST works — no
# browser needed).
#
# PASS: prefix unknown (fresh) or bound to exactly this URI (re-deploy).
# FAIL: prefix bound to a different URI, or URI bound to a different prefix.
#
# Usage: namespace-check.sh <prefix> <uri> [project_path]
#   e.g. namespace-check.sh acq 'https://jahia.com/acquia-drupal/nt/1.0'
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
prefix="${1:?prefix required (e.g. acq)}"
uri="${2:?namespace URI required}"
load_env "${3:-}"

HOST="${JAHIA_URL:-${JAHIA_HOST:-http://localhost:8080}}"
HOST="${HOST%/}"
USERPASS="${JAHIA_USER:-root}"
[[ "$USERPASS" == *:* ]] || USERPASS="$USERPASS:${JAHIA_PASS:-root}"

dump="$(curl -sf -u "$USERPASS" -H "Origin: $HOST" -X POST \
  "$HOST/modules/tools/groovyConsole.jsp" \
  --data-urlencode "script=
def reg = org.jahia.services.content.JCRSessionFactory.getInstance().getCurrentUserSession().getWorkspace().getNamespaceRegistry()
println 'NSDUMP-BEGIN'
reg.getPrefixes().each { p -> println p + '|' + reg.getURI(p) }
println 'NSDUMP-END'
" --data "runScript=true")" || fail "Groovy console unreachable at $HOST (check JAHIA_URL/credentials in .env.local)"

# first BEGIN..END block only — the tools page echoes the script back afterwards
table="$(printf '%s\n' "$dump" | awk '/NSDUMP-END/{exit} on{print} /NSDUMP-BEGIN/{on=1}')"
[ -n "$table" ] || fail "could not parse namespace registry dump (Groovy output changed?)"

registered_uri="$(printf '%s\n' "$table" | awk -F'|' -v p="$prefix" '$1==p{print $2; exit}')"
registered_prefix="$(printf '%s\n' "$table" | awk -F'|' -v u="$uri" '$2==u{print $1; exit}')"

if [ -n "$registered_uri" ] && [ "$registered_uri" != "$uri" ]; then
  fail "prefix '$prefix' already registered with DIFFERENT uri: $registered_uri (wanted $uri) — pick a fresh prefix (registry survives uninstalls)"
fi
if [ -n "$registered_prefix" ] && [ "$registered_prefix" != "$prefix" ]; then
  fail "uri '$uri' already bound to prefix '$registered_prefix' (wanted $prefix)"
fi
if [ -n "$registered_uri" ]; then
  pass "namespace '$prefix' already registered with matching uri (re-deploy OK)"
fi
pass "namespace '$prefix' is free on $HOST"
