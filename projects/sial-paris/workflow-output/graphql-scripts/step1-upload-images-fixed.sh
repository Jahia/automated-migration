#!/bin/bash
set -e

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 1 — Upload images to DAM ==="

# Create images folder using simple mutation
echo ""
echo "1. Create /images folder..."
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  -d '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/files\") { addChild(name: \"images\", primaryNodeType: \"jnt:folder\") { uuid } } } }"}' > /dev/null 2>&1 || true
echo "OK: images folder"

sleep 0.5

# Upload logo-header.jpg using form data
echo ""
echo "2. Upload logo-header.jpg..."
LOGO_RESPONSE=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" \
  -F 'query=mutation($file: Upload!) { jcr(workspace: EDIT) { addNode(name: "logo-header.jpg", parentPathOrId: "/sites/sial-paris/files/images", primaryNodeType: "jnt:file", mixins: ["jmix:image"]) { addChild(name: "jcr:content", primaryNodeType: "jnt:resource") { mutateProperty(name: "jcr:data") { setValue(type: BINARY, value: $file) } mutateProperty(name: "jcr:mimeType") { setValue(value: "image/jpeg") } } uuid } } }' \
  -F 'variables={"file":null}' \
  -F 'file=@/Users/stephane/Runtimes/0.Modules/jahiaMigration/projects/sial-paris/static/assets/logo-header.jpg')
echo "$LOGO_RESPONSE" | grep -q "uuid" && echo "OK: logo-header.jpg uploaded" || echo "FAIL: logo-header.jpg"
LOGO_UUID=$(echo "$LOGO_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['addNode']['uuid'])" 2>/dev/null || echo "unknown")
echo "   UUID: $LOGO_UUID"

sleep 0.5

# Upload video-thumbnail.jpg
echo ""
echo "3. Upload video-thumbnail.jpg..."
THUMB_RESPONSE=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" \
  -F 'query=mutation($file: Upload!) { jcr(workspace: EDIT) { addNode(name: "video-thumbnail.jpg", parentPathOrId: "/sites/sial-paris/files/images", primaryNodeType: "jnt:file", mixins: ["jmix:image"]) { addChild(name: "jcr:content", primaryNodeType: "jnt:resource") { mutateProperty(name: "jcr:data") { setValue(type: BINARY, value: $file) } mutateProperty(name: "jcr:mimeType") { setValue(value: "image/jpeg") } } uuid } } }' \
  -F 'variables={"file":null}' \
  -F 'file=@/Users/stephane/Runtimes/0.Modules/jahiaMigration/projects/sial-paris/static/assets/video-thumbnail.jpg')
echo "$THUMB_RESPONSE" | grep -q "uuid" && echo "OK: video-thumbnail.jpg uploaded" || echo "FAIL: video-thumbnail.jpg"
THUMB_UUID=$(echo "$THUMB_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['addNode']['uuid'])" 2>/dev/null || echo "unknown")
echo "   UUID: $THUMB_UUID"

sleep 0.5

# Query and save
echo ""
echo "4. Verify images..."
QUERY=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  -d '{"query":"{ jcr(workspace: EDIT) { nodeByPath(path: \"/sites/sial-paris/files/images\") { children { nodes { name uuid } } } } }"}')
echo "$QUERY" | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
nodes = d.get('data', {}).get('jcr', {}).get('nodeByPath', {}).get('children', {}).get('nodes', [])
print(f"Found {len(nodes)} images")
result = {n['name']: n['uuid'] for n in nodes}
with open('/tmp/sial-paris-images.json', 'w') as f:
  json.dump(result, f, indent=2)
for name, uuid in result.items():
  print(f"  {name}: {uuid}")
PYTHON

echo ""
echo "5. Publish images..."
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  -d '{"query":"mutation { jcr { mutateNode(pathOrId: \"/sites/sial-paris/files/images\") { publish(publishSubNodes: true) } } }"}' > /dev/null
echo "OK: published"

echo ""
echo "=== STEP 1 COMPLETE ==="
