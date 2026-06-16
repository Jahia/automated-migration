#!/bin/bash
set -e

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"
SITE_NAME="sial-paris"
LANG="fr"

echo "=== STEP 1 — Upload images to DAM ==="

# Helper function to verify response
verify_response() {
  local resp="$1" label="$2"
  if echo "$resp" | grep -q '"errors"'; then
    echo "FAIL: $label — $(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['errors'][0]['message'][:200])" 2>/dev/null || echo "unknown error")"
    return 1
  fi
  echo "OK: $label"
}

# Create images folder if needed
echo ""
echo "1. Create /images folder..."
resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" \
  -H "content-type: application/json" \
  -d '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/sial-paris/files\") { addChild(name: \"images\", primaryNodeType: \"jnt:folder\") { uuid } } } }"}' 2>/dev/null || echo '{"data":{"jcr":{"mutateNode":{"addChild":{"uuid":"exists"}}}}}')
verify_response "$resp" "create images folder"

# Upload logo-header.jpg
echo ""
echo "2. Upload logo-header.jpg..."
IMG1_RESP=$(curl -s -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" \
  -X POST "$JAHIA_HOST/modules/graphql" \
  -F 'operations={"query":"mutation uploadFile($nameInJCR: String!, $path: String!, $mimeType: String!, $fileHandle: String!) { jcr(workspace: EDIT) { addNode(name: $nameInJCR, parentPathOrId: $path, primaryNodeType: \"jnt:file\", mixins: [\"jmix:image\"]) { addChild(name: \"jcr:content\", primaryNodeType: \"jnt:resource\") { content: mutateProperty(name: \"jcr:data\") { setValue(type: BINARY, value: $fileHandle) } contentType: mutateProperty(name: \"jcr:mimeType\") { setValue(value: $mimeType) } } uuid } } }","variables":{"nameInJCR":"logo-header.jpg","path":"/sites/sial-paris/files/images","mimeType":"image/jpeg","fileHandle":"fc"}}' \
  -F 'map={"fc":["variables.fileHandle"]}' \
  -F "fc=@/Users/stephane/Runtimes/0.Modules/jahiaMigration/projects/sial-paris/static/assets/logo-header.jpg;type=image/jpeg")
verify_response "$IMG1_RESP" "upload logo-header.jpg"
IMG1_UUID=$(echo "$IMG1_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['addNode']['uuid'])" 2>/dev/null)
echo "   UUID: $IMG1_UUID"

sleep 0.5

# Upload video-thumbnail.jpg
echo ""
echo "3. Upload video-thumbnail.jpg..."
IMG2_RESP=$(curl -s -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" \
  -X POST "$JAHIA_HOST/modules/graphql" \
  -F 'operations={"query":"mutation uploadFile($nameInJCR: String!, $path: String!, $mimeType: String!, $fileHandle: String!) { jcr(workspace: EDIT) { addNode(name: $nameInJCR, parentPathOrId: $path, primaryNodeType: \"jnt:file\", mixins: [\"jmix:image\"]) { addChild(name: \"jcr:content\", primaryNodeType: \"jnt:resource\") { content: mutateProperty(name: \"jcr:data\") { setValue(type: BINARY, value: $fileHandle) } contentType: mutateProperty(name: \"jcr:mimeType\") { setValue(value: $mimeType) } } uuid } } }","variables":{"nameInJCR":"video-thumbnail.jpg","path":"/sites/sial-paris/files/images","mimeType":"image/jpeg","fileHandle":"fc"}}' \
  -F 'map={"fc":["variables.fileHandle"]}' \
  -F "fc=@/Users/stephane/Runtimes/0.Modules/jahiaMigration/projects/sial-paris/static/assets/video-thumbnail.jpg;type=image/jpeg")
verify_response "$IMG2_RESP" "upload video-thumbnail.jpg"
IMG2_UUID=$(echo "$IMG2_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['jcr']['addNode']['uuid'])" 2>/dev/null)
echo "   UUID: $IMG2_UUID"

sleep 0.5

# Query final UUIDs and save to file
echo ""
echo "4. Query final image UUIDs..."
QUERY_RESP=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  -d '{"query":"{ jcr(workspace: EDIT) { nodeByPath(path: \"/sites/sial-paris/files/images\") { children { nodes { name uuid } } } } }"}')
echo "$QUERY_RESP" | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
nodes = d.get('data', {}).get('jcr', {}).get('nodeByPath', {}).get('children', {}).get('nodes', [])
result = {n['name']: n['uuid'] for n in nodes}
with open('/tmp/sial-paris-images.json', 'w') as f:
  json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
PYTHON

# Publish images
echo ""
echo "5. Publish images folder..."
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  -d '{"query":"mutation { jcr { mutateNode(pathOrId: \"/sites/sial-paris/files/images\") { publish(publishSubNodes: true) } } }"}' > /dev/null
echo "OK: published images folder"

echo ""
echo "=== STEP 1 COMPLETE ==="
