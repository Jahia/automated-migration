#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 9 — Final publish of home page and all content ==="

publish_node() {
  local path="$1"
  curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$path\\\") { publish(publishSubNodes: true) } } }\"}" > /dev/null
  echo "Published: $path"
}

echo ""
echo "Publishing main content areas..."
publish_node "/sites/sial-paris/home/main"
publish_node "/sites/sial-paris/home"

echo ""
echo "Publishing news folder..."
publish_node "/sites/sial-paris/contents/news"

echo ""
echo "=== STEP 9 COMPLETE ==="
