#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 6 — Create main area components ==="

verify_response() {
  local resp="$1" label="$2"
  if echo "$resp" | grep -q '"errors"'; then
    echo "FAIL: $label"
    return 1
  fi
  echo "OK: $label"
}

publish_node() {
  local path="$1"
  curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$path\\\") { publish(publishSubNodes: true) } } }\"}" > /dev/null
  echo "Published: $path"
}

# 1. introText
echo ""
echo "1. Creating introText..."
intro_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/main\") { addChild(name: \"introText\", primaryNodeType: \"sialp:introText\") { uuid } } } }"}')
verify_response "$intro_resp" "create introText"

INTRO_UUID=$(echo "$intro_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.2

intro_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$INTRO_UUID\\\") { p1: mutateProperty(name: \\\"overline\\\") { setValue(language: \\\"fr\\\", value: \\\"LE SALON MONDIAL\\\") } p2: mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"SIAL Paris, le rendez-vous mondial de l'alimentation\\\") } p3: mutateProperty(name: \\\"body\\\") { setValue(language: \\\"fr\\\", value: \\\"Tous les 2 ans à Paris Nord Villepinte, SIAL Paris réunit les acteurs de l'industrie alimentaire mondiale pour 5 jours d'innovation, de tendances et de rencontres professionnelles. 7 500 exposants, 400 000 produits présentés, 200 000 visiteurs de 200 pays.\\\") } } } }\"}")
verify_response "$intro_prop" "set introText properties"
publish_node "/sites/sial-paris/home/main/introText"

# 2. keyFigures
echo ""
echo "2. Creating keyFigures..."
key_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/main\") { addChild(name: \"keyFigures\", primaryNodeType: \"sialp:keyFigures\") { uuid } } } }"}')
verify_response "$key_resp" "create keyFigures"

KEY_UUID=$(echo "$key_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.3

# Create key figures
create_figure() {
  local name="$1" number="$2" unit="$3" label="$4"
  fig_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$KEY_UUID\\\") { addChild(name: \\\"$name\\\", primaryNodeType: \\\"sialp:keyFigure\\\", properties: [{name: \\\"number\\\", value: \\\"$number\\\"}]) { uuid } } } }\"}")
  verify_response "$fig_resp" "create figure $name"
  FIG_UUID=$(echo "$fig_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
  sleep 0.2
  
  fig_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$FIG_UUID\\\") { p1: mutateProperty(name: \\\"unit\\\") { setValue(language: \\\"fr\\\", value: \\\"$unit\\\") } p2: mutateProperty(name: \\\"label\\\") { setValue(language: \\\"fr\\\", value: \\\"$label\\\") } } } }\"}")
  verify_response "$fig_prop" "set figure $name properties"
  sleep 0.1
}

create_figure "fig1" "7 500" "" "exposants"
create_figure "fig2" "200" "pays" "représentés"
create_figure "fig3" "400 000" "" "produits"
create_figure "fig4" "200 000" "" "visiteurs"
create_figure "fig5" "5" "jours" "d'événement"

publish_node "/sites/sial-paris/home/main/keyFigures"

# 3. newsListing
echo ""
echo "3. Creating newsListing..."
news_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/main\") { addChild(name: \"newsListing\", primaryNodeType: \"sialp:newsListing\", properties: [{name: \"maxItems\", value: \"3\"}]) { uuid } } } }"}')
verify_response "$news_resp" "create newsListing"

NEWS_UUID=$(echo "$news_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.2

news_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$NEWS_UUID\\\") { p1: mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"Dernières actualités\\\") } p2: mutateProperty(name: \\\"ctaLabel\\\") { setValue(language: \\\"fr\\\", value: \\\"Voir toutes les actualités\\\") } } } }\"}")
verify_response "$news_prop" "set newsListing properties"
publish_node "/sites/sial-paris/home/main/newsListing"

echo ""
echo "=== STEP 6 COMPLETE ==="
