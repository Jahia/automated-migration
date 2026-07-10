#!/bin/bash
set -e

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"
SITE_NAME="sial-paris"
LANG="fr"

echo "=== STEP 2 — Create sitemap pages ==="

verify_response() {
  local resp="$1" label="$2"
  if echo "$resp" | grep -q '"errors"'; then
    MSG=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['errors'][0]['message'][:150])" 2>/dev/null || echo "unknown error")
    echo "FAIL: $label — $MSG"
    return 1
  fi
  echo "OK: $label"
}

create_page() {
  local name="$1" title_fr="$2"
  echo ""
  echo "Creating page: $name ($title_fr)..."
  
  resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Accept-Language: fr" -H "Origin: $JAHIA_HOST" \
    -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H "accept: application/json, multipart/mixed" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/sial-paris/home\\\") { addChild(name: \\\"$name\\\", primaryNodeType: \\\"jnt:page\\\", properties: [{name: \\\"j:templateName\\\", value: \\\"basic\\\"}]) { addChild(name: \\\"j:translation_fr\\\", primaryNodeType: \\\"jnt:translation\\\", properties: [{name: \\\"jcr:language\\\", value: \\\"fr\\\"}, {name: \\\"jcr:title\\\", value: \\\"$title_fr\\\"}]) { uuid } uuid } } } }\"}")
  
  verify_response "$resp" "create page $name"
  
  # Extract UUID for publishing
  PAGE_UUID=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
  
  # Publish page
  sleep 0.3
  pub_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Accept-Language: fr" -H "Origin: $JAHIA_HOST" \
    -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H "accept: application/json, multipart/mixed" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/sial-paris/home/$name\\\") { publish(publishSubNodes: true) } } }\"}")
  
  verify_response "$pub_resp" "publish page $name"
}

# Create pages
create_page "le-salon" "Le Salon"
create_page "les-exposants" "Les Exposants 2026"
create_page "temps-forts" "Temps Forts"
create_page "tendances" "Tendances"
create_page "infos-pratiques" "Infos Pratiques"
create_page "medias" "Médias"

# Update home page title
echo ""
echo "Updating home page title..."
home_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Accept-Language: fr" -H "Origin: $JAHIA_HOST" \
  -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H "accept: application/json, multipart/mixed" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home\") { setPropertiesI18N(language: \"fr\", properties: [{name: \"jcr:title\", value: \"SIAL Paris 2026 - Le salon mondial de l'"'"'alimentation\"}]) { uuid } } } }"}')
verify_response "$home_resp" "update home page title"

echo ""
echo "=== STEP 2 COMPLETE ==="
