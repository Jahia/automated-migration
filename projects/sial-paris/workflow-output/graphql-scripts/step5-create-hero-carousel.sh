#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 5 — Create hero carousel and slides ==="

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

# Create heroCarousel
echo ""
echo "Creating heroCarousel..."
carousel_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/hero\") { addChild(name: \"heroCarousel\", primaryNodeType: \"sialp:heroCarousel\") { uuid } } } }"}')
verify_response "$carousel_resp" "create heroCarousel"

CAROUSEL_UUID=$(echo "$carousel_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
echo "Carousel UUID: $CAROUSEL_UUID"
sleep 0.3

create_slide() {
  local name="$1" badge="$2" heading="$3" body="$4" cta="$5"
  echo ""
  echo "Creating slide: $name..."
  resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$CAROUSEL_UUID\\\") { addChild(name: \\\"$name\\\", primaryNodeType: \\\"sialp:heroSlide\\\") { uuid } } } }\"}")
  
  verify_response "$resp" "create slide $name"
  SLIDE_UUID=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
  sleep 0.2
  
  # Set properties
  prop_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$SLIDE_UUID\\\") { p1: mutateProperty(name: \\\"badge\\\") { setValue(language: \\\"fr\\\", value: \\\"$badge\\\") } p2: mutateProperty(name: \\\"heading\\\") { setValue(language: \\\"fr\\\", value: \\\"$heading\\\") } p3: mutateProperty(name: \\\"body\\\") { setValue(language: \\\"fr\\\", value: \\\"$body\\\") } p4: mutateProperty(name: \\\"ctaLabel\\\") { setValue(language: \\\"fr\\\", value: \\\"$cta\\\") } } } }\"}")
  
  verify_response "$prop_resp" "set properties on slide $name"
  sleep 0.2
}

# Create 3 slides
create_slide "slide1" "17 - 21 OCT. 2026" "Le salon mondial de l'alimentation" "Paris Nord Villepinte" "Découvrir"
create_slide "slide2" "SIAL Innovation 2026" "Les innovations alimentaires de demain" "Découvrez les tendances qui façonnent le secteur" "En savoir plus"
create_slide "slide3" "SIAL for Change" "Un salon engagé pour une alimentation durable" "Retrouvez nos initiatives RSE et développement durable" "Notre engagement"

echo ""
publish_node "/sites/sial-paris/home/hero/heroCarousel"
publish_node "/sites/sial-paris/home/hero"

echo ""
echo "=== STEP 5 COMPLETE ==="
