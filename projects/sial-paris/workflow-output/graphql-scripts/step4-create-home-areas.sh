#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 4 — Create home page content areas ==="

verify_response() {
  local resp="$1" label="$2"
  if echo "$resp" | grep -q '"errors"'; then
    echo "FAIL: $label — $(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('errors',[{}])[0].get('message','')[:100])" 2>/dev/null)"
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

# Create hero area
echo ""
echo "Creating hero area..."
resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home\") { addChild(name: \"hero\", primaryNodeType: \"jnt:contentList\") { uuid } } } }"}')
verify_response "$resp" "create hero area"

# Create main area
echo "Creating main area..."
resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home\") { addChild(name: \"main\", primaryNodeType: \"jnt:contentList\") { uuid } } } }"}')
verify_response "$resp" "create main area"

echo ""
echo "=== STEP 4 COMPLETE ==="
