#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 3 — Create header and footer ==="

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

# Create header area
echo ""
echo "Creating header area..."
resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home\") { addChild(name: \"header\", primaryNodeType: \"jnt:contentList\") { uuid } } } }"}')
verify_response "$resp" "create header area"
sleep 0.3

# Create mainNavigation
echo "Creating mainNavigation..."
nav_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/header\") { addChild(name: \"mainNavigation\", primaryNodeType: \"sialp:mainNavigation\") { uuid } } } }"}')
verify_response "$nav_resp" "create mainNavigation"

NAV_UUID=$(echo "$nav_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.3

# Set mainNavigation properties
echo "Setting mainNavigation properties..."
prop_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$NAV_UUID\\\") { p1: mutateProperty(name: \\\"exposantCtaLabel\\\") { setValue(language: \\\"fr\\\", value: \\\"J'EXPOSE\\\") } p2: mutateProperty(name: \\\"visiteurCtaLabel\\\") { setValue(language: \\\"fr\\\", value: \\\"JE VISITE\\\") } } } }\"}")
verify_response "$prop_resp" "set mainNavigation properties"

publish_node "/sites/sial-paris/home/header/mainNavigation"
publish_node "/sites/sial-paris/home/header"

# Create footer area
echo ""
echo "Creating footer area..."
ft_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home\") { addChild(name: \"footer\", primaryNodeType: \"jnt:contentList\") { uuid } } } }"}')
verify_response "$ft_resp" "create footer area"
sleep 0.3

# Create footer node
echo "Creating footer node..."
footer_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/home/footer\") { addChild(name: \"footer\", primaryNodeType: \"sialp:footer\") { uuid } } } }"}')
verify_response "$footer_resp" "create footer node"

FOOTER_UUID=$(echo "$footer_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['mutateNode']['addChild']['uuid'])" 2>/dev/null)
sleep 0.3

# Set footer properties
echo "Setting footer properties..."
fprop_resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$FOOTER_UUID\\\") { p1: mutateProperty(name: \\\"newsletterHeading\\\") { setValue(language: \\\"fr\\\", value: \\\"Restez informé\\\") } p2: mutateProperty(name: \\\"newsletterPlaceholder\\\") { setValue(language: \\\"fr\\\", value: \\\"Votre adresse email\\\") } p3: mutateProperty(name: \\\"copyrightText\\\") { setValue(language: \\\"fr\\\", value: \\\"© 2026 SIAL Paris - Comexposium\\\") } } } }\"}")
verify_response "$fprop_resp" "set footer properties"

publish_node "/sites/sial-paris/home/footer/footer"
publish_node "/sites/sial-paris/home/footer"

echo ""
echo "=== STEP 3 COMPLETE ==="
