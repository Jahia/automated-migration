#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 7 — Create remaining main components ==="

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

# 4. visitorProfiles
echo ""
echo "4. Creating visitorProfiles..."
visit_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/main\") { addChild(name: \"visitorProfiles\", primaryNodeType: \"sialp:visitorProfiles\") { uuid } } } }"}')
verify_response "$visit_resp" "create visitorProfiles"

VISIT_UUID=$(echo "$visit_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.2

# Set heading
visit_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$VISIT_UUID\\\") { mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"Qui visite SIAL Paris ?\\\") } } } }\"}")
verify_response "$visit_prop" "set visitorProfiles heading"
sleep 0.2

# Create profiles
create_profile() {
  local name="$1" heading="$2" desc="$3"
  prof_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$VISIT_UUID\\\") { addChild(name: \\\"$name\\\", primaryNodeType: \\\"sialp:visitorProfile\\\") { uuid } } } }\"}")
  verify_response "$prof_resp" "create profile $name"
  PROF_UUID=$(echo "$prof_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
  sleep 0.2
  
  prof_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$PROF_UUID\\\") { p1: mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"$heading\\\") } p2: mutateProperty(name: \\\"description\\\") { setValue(language: \\\"fr\\\", value: \\\"$desc\\\") } p3: mutateProperty(name: \\\"ctaLabel\\\") { setValue(language: \\\"fr\\\", value: \\\"En savoir plus\\\") } } } }\"}")
  verify_response "$prof_prop" "set profile $name properties"
  sleep 0.1
}

create_profile "distributeurs" "Distributeurs" "GMS, hard discount, e-commerce, cash & carry, restauration collective"
create_profile "industriels" "Industriels" "Fabricants, transformateurs, marques de distributeur"
create_profile "restaurateurs" "Restaurateurs" "CHR, gastronomie, restauration rapide, traiteurs"
create_profile "grandpublic" "Grand public" "Journées grand public, animations, dégustations"

publish_node "/sites/sial-paris/home/main/visitorProfiles"

# 5. trendsSection
echo ""
echo "5. Creating trendsSection..."
trend_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/main\") { addChild(name: \"trendsSection\", primaryNodeType: \"sialp:trendsSection\") { uuid } } } }"}')
verify_response "$trend_resp" "create trendsSection"

TREND_UUID=$(echo "$trend_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.2

trend_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$TREND_UUID\\\") { p1: mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"Tendances & Innovations\\\") } p2: mutateProperty(name: \\\"intro\\\") { setValue(language: \\\"fr\\\", value: \\\"SIAL Paris est l'observatoire mondial des tendances alimentaires. Décryptez les grandes évolutions qui transforment l'industrie.\\\") } p3: mutateProperty(name: \\\"ctaLabel\\\") { setValue(language: \\\"fr\\\", value: \\\"Toutes les tendances\\\") } } } }\"}")
verify_response "$trend_prop" "set trendsSection properties"
sleep 0.2

# Create trends
create_trend() {
  local name="$1" tag="$2" heading="$3" excerpt="$4"
  trd_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$TREND_UUID\\\") { addChild(name: \\\"$name\\\", primaryNodeType: \\\"sialp:trendCard\\\") { uuid } } } }\"}")
  verify_response "$trd_resp" "create trend $name"
  TRD_UUID=$(echo "$trd_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
  sleep 0.2
  
  trd_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$TRD_UUID\\\") { p1: mutateProperty(name: \\\"tag\\\") { setValue(language: \\\"fr\\\", value: \\\"$tag\\\") } p2: mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"$heading\\\") } p3: mutateProperty(name: \\\"excerpt\\\") { setValue(language: \\\"fr\\\", value: \\\"$excerpt\\\") } } } }\"}")
  verify_response "$trd_prop" "set trend $name properties"
  sleep 0.1
}

create_trend "trend1" "Durabilité" "Alimentation durable : les nouvelles protéines végétales" "Le marché des protéines alternatives continue sa croissance avec de nouvelles solutions innovantes."
create_trend "trend2" "Santé" "Nutriscore et reformulation : où en est l'industrie ?" "Les fabricants accélèrent la reformulation de leurs recettes pour répondre aux attentes consommateurs."
create_trend "trend3" "Tech" "Food tech : l'IA au service de la production alimentaire" "Les startups food tech intègrent l'intelligence artificielle pour optimiser les process de production."

publish_node "/sites/sial-paris/home/main/trendsSection"

# 6. videoSection
echo ""
echo "6. Creating videoSection..."
video_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/main\") { addChild(name: \"videoSection\", primaryNodeType: \"sialp:videoSection\", properties: [{name: \"videoUrl\", value: \"https://www.youtube.com/embed/sparis2024\"}]) { uuid } } } }"}')
verify_response "$video_resp" "create videoSection"

VIDEO_UUID=$(echo "$video_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.2

video_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$VIDEO_UUID\\\") { mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"SIAL Paris 2024 en images\\\") } } } }\"}")
verify_response "$video_prop" "set videoSection properties"
publish_node "/sites/sial-paris/home/main/videoSection"

# 7. ctaDualCards
echo ""
echo "7. Creating ctaDualCards..."
cta_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/main\") { addChild(name: \"ctaDualCards\", primaryNodeType: \"sialp:ctaDualCards\") { uuid } } } }"}')
verify_response "$cta_resp" "create ctaDualCards"

CTA_UUID=$(echo "$cta_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.2

cta_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$CTA_UUID\\\") { p1: mutateProperty(name: \\\"leftHeading\\\") { setValue(language: \\\"fr\\\", value: \\\"Vous exposez à SIAL Paris 2026 ?\\\") } p2: mutateProperty(name: \\\"leftCtaLabel\\\") { setValue(language: \\\"fr\\\", value: \\\"Je dépose ma candidature\\\") } p3: mutateProperty(name: \\\"rightHeading\\\") { setValue(language: \\\"fr\\\", value: \\\"Vous visitez SIAL Paris 2026 ?\\\") } p4: mutateProperty(name: \\\"rightCtaLabel\\\") { setValue(language: \\\"fr\\\", value: \\\"Je commande mon badge\\\") } } } }\"}")
verify_response "$cta_prop" "set ctaDualCards properties"
publish_node "/sites/sial-paris/home/main/ctaDualCards"

# 8. sialNetwork
echo ""
echo "8. Creating sialNetwork..."
net_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/main\") { addChild(name: \"sialNetwork\", primaryNodeType: \"sialp:sialNetwork\") { uuid } } } }"}')
verify_response "$net_resp" "create sialNetwork"

NET_UUID=$(echo "$net_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.2

net_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$NET_UUID\\\") { mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"Le réseau SIAL mondial\\\") } } } }\"}")
verify_response "$net_prop" "set sialNetwork heading"
sleep 0.2

# Create network events
create_event() {
  local name="$1" eventName="$2" city="$3"
  evt_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$NET_UUID\\\") { addChild(name: \\\"$name\\\", primaryNodeType: \\\"sialp:networkEvent\\\", properties: [{name: \\\"eventName\\\", value: \\\"$eventName\\\"}, {name: \\\"city\\\", value: \\\"$city\\\"}]) { uuid } } } }\"}")
  verify_response "$evt_resp" "create event $name"
  sleep 0.1
}

create_event "sial-paris" "SIAL Paris" "Paris"
create_event "sial-canada" "SIAL Canada" "Montréal / Toronto"
create_event "sial-china" "SIAL China" "Shanghai"
create_event "sial-india" "SIAL India" "New Delhi"
create_event "sial-interfood" "SIAL Interfood" "Jakarta"
create_event "sial-me" "SIAL Middle East" "Abu Dhabi"
create_event "sial-network" "SIAL Network" "International"

publish_node "/sites/sial-paris/home/main/sialNetwork"

echo ""
echo "=== STEP 7 COMPLETE ==="
