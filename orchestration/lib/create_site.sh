#!/usr/bin/env bash
# create_site.sh — site creation via the PROVISIONING API (never GraphQL addNode).
#
# Rule (jahia.md 19): a hand-made jnt:virtualsite node misses home page, ACLs,
# files/groups folders, template-set binding and installed modules. Only the
# provisioning `createSite` action initializes all of it. After creating we
# VERIFY the invariants (same rule): j:languages, home/files/contents/groups
# children, template set binding.
#
# Idempotent: if the site already exists, creation is skipped, verification runs.
#
# Usage: create_site.sh <siteKey> <title> <templateSet> [langs-csv] [serverName]
#   e.g. create_site.sh acquia "Acquia (migrated)" acquia-drupal en,fr localhost
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../probes/_lib.sh
source "$HERE/../probes/_lib.sh"
site="${1:?siteKey required}"
title="${2:?title required}"
tset="${3:?templateSet (module name) required}"
langs="${4:-en,fr}"
server="${5:-localhost}"
load_env ""

HOST="${JAHIA_URL:-${JAHIA_HOST:-http://localhost:8080}}"
HOST="${HOST%/}"
USERPASS="${JAHIA_USER:-root}"
[[ "$USERPASS" == *:* ]] || USERPASS="$USERPASS:${JAHIA_PASS:-root}"
deflang="${langs%%,*}"

gql() {
  curl -sf -u "$USERPASS" -H "Origin: $HOST" -H 'Content-Type: application/json' \
    -X POST "$HOST/modules/graphql" -d "{\"query\":$(printf '%s' "$1" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}"
}

site_exists() {
  gql "{ jcr { nodeByPath(path: \"/sites/$site\") { uuid } } }" 2>/dev/null \
    | grep -q '"uuid"'
}

wrong_templateset() {
  # a site created while its template-set module was still starting can end up
  # bound to ANOTHER templateSet (observed live: supercarv2 bound to
  # acquia-drupal -> 'Couldn't find the template associated with site', HTTP
  # 500 on every page). JCR-patching j:templatesSet does NOT repair the
  # runtime association (rule 19) — the ONLY clean fix is deleteSite+createSite.
  gql "{ jcr { nodeByPath(path: \"/sites/$site\") { tpl: property(name: \"j:templatesSet\") { value } } }
  }" 2>/dev/null | grep -q "\"value\"" && \
  ! gql "{ jcr { nodeByPath(path: \"/sites/$site\") { tpl: property(name: \"j:templatesSet\") { value } } } }" 2>/dev/null | grep -q "\"$tset\""
}

if site_exists && wrong_templateset; then
  echo "[create_site] site '$site' exists with the WRONG templateSet — deleteSite + recreate"
  printf -- "- deleteSite: \"\"\n  siteKey: %s\n" "$site" | curl -sf -u "$USERPASS" \
    -H "Origin: $HOST" -H 'Content-Type: application/yaml' --data-binary @- \
    "$HOST/modules/api/provisioning" >/dev/null \
    || fail "provisioning deleteSite failed for $site"
  sleep 2
fi

if site_exists; then
  echo "[create_site] site '$site' already exists — skipping creation, verifying"
else
  # languages must be a YAML LIST — a csv string silently yields default-only
  # (observed live: languages: "en,fr" -> j:languages=[en])
  langs_yaml=""
  for l in ${langs//,/ }; do langs_yaml="$langs_yaml
    - $l"; done
  yaml="- createSite: \"\"
  siteKey: $site
  title: \"$title\"
  serverName: $server
  templateSet: $tset
  defaultLanguage: $deflang
  languages:$langs_yaml
"
  echo "[create_site] POST /modules/api/provisioning (createSite $site, templateSet=$tset)"
  out="$(printf '%s' "$yaml" | curl -sf -u "$USERPASS" -H "Origin: $HOST" \
        -H 'Content-Type: application/yaml' --data-binary @- \
        "$HOST/modules/api/provisioning")" \
    || fail "provisioning API call failed (is module '$tset' deployed and started?)"
  [ -n "$out" ] && echo "$out" | head -3
  # provisioning createSite has NO languages parameter (verified in the Jahia
  # log: SiteCreationInfo carries locale only) — set j:languages right after
  vals=""
  for l in ${langs//,/ }; do vals="$vals\\\"$l\\\", "; done
  vals="${vals%, }"
  gql "mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/$site\") { p: mutateProperty(name: \"j:languages\") { setValues(values: [$vals]) } } } }" >/dev/null \
    || echo "[create_site] WARN: post-create language set failed"
fi

# ── rule-19 invariants ──
resp="$(gql "{ jcr { nodeByPath(path: \"/sites/$site\") {
  uuid
  languages: property(name: \"j:languages\") { values }
  modules: property(name: \"j:installedModules\") { values }
  children { nodes { name } }
} } }")" || fail "site '$site' not found after creation"

echo "$resp" | grep -q '"uuid"' || fail "site node /sites/$site missing"
for l in ${langs//,/ }; do
  echo "$resp" | grep -q "\"$l\"" || fail "j:languages missing '$l' on /sites/$site"
done
echo "$resp" | grep -q "\"$tset\"" || fail "j:installedModules missing template set '$tset'"
for child in home files contents groups; do
  echo "$resp" | grep -q "\"name\":\"$child\"" \
    || echo "$resp" | grep -q "\"name\": \"$child\"" \
    || fail "child '$child' missing under /sites/$site (site not fully initialized)"
done
pass "site '$site' exists and is fully initialized (langs=$langs, templateSet=$tset, home/files/contents/groups present)"
