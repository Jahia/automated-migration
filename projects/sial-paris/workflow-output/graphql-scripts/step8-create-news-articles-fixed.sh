#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 8 — Create news articles ==="

verify_response() {
  local resp="$1" label="$2"
  if echo "$resp" | grep -q '"errors"'; then
    echo "FAIL: $label — $(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('errors',[{}])[0].get('message','unknown')[:80])" 2>/dev/null)"
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

create_article() {
  local name="$1" title="$2" category="$3" date="$4" excerpt="$5" body="$6"
  echo ""
  echo "Creating article: $name..."
  
  # Create article node with date and properties
  article_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/sial-paris/contents/news\\\") { addChild(name: \\\"$name\\\", primaryNodeType: \\\"sialp:newsArticle\\\") { uuid } } } }\"}")
  verify_response "$article_resp" "create article $name"
  
  ARTICLE_UUID=$(echo "$article_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
  sleep 0.2
  
  # Set date and category (category is i18n)
  date_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$ARTICLE_UUID\\\") { p1: mutateProperty(name: \\\"publishDate\\\") { setValue(value: \\\"${date}T00:00:00.000Z\\\", type: DATE) } p2: mutateProperty(name: \\\"category\\\") { setValue(language: \\\"fr\\\", value: \\\"$category\\\") } } } }\"}")
  verify_response "$date_resp" "set date and category on $name"
  sleep 0.2
  
  # Set i18n properties
  article_prop=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$ARTICLE_UUID\\\") { p1: mutateProperty(name: \\\"title\\\") { setValue(language: \\\"fr\\\", value: \\\"$title\\\") } p2: mutateProperty(name: \\\"excerpt\\\") { setValue(language: \\\"fr\\\", value: \\\"$excerpt\\\") } p3: mutateProperty(name: \\\"body\\\") { setValue(language: \\\"fr\\\", value: \\\"$body\\\") } } } }\"}")
  verify_response "$article_prop" "set article $name properties"
  
  sleep 0.3
  publish_node "/sites/sial-paris/contents/news/$name"
}

create_article "sial-innovation-2026" \
  "SIAL Innovation 2026 : les candidatures sont ouvertes" \
  "Innovation" "2026-03-15" \
  "Les entreprises du secteur alimentaire peuvent désormais soumettre leurs innovations pour le concours SIAL Innovation 2026." \
  "Les entreprises du secteur alimentaire peuvent désormais soumettre leurs innovations."

create_article "rapport-tendances-2026" \
  "Rapport tendances 2026 : les 5 grands enjeux de l'alimentaire" \
  "Tendances" "2026-02-28" \
  "Notre rapport annuel dévoile les grandes tendances qui vont façonner le marché alimentaire mondial en 2026." \
  "Notre rapport annuel dévoile les grandes tendances."

create_article "j-200-exposants" \
  "SIAL Paris 2026 : J-200, les inscriptions exposants progressent" \
  "Événement" "2026-04-01" \
  "À 200 jours de l'ouverture du salon, le nombre d'exposants inscrits dépasse déjà les chiffres de 2024 à la même période." \
  "À 200 jours de l'ouverture du salon, le nombre d'exposants progresse."

echo ""
echo "=== STEP 8 COMPLETE ==="
