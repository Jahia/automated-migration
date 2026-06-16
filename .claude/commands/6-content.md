---
description: Create pages, components, and content via Jahia GraphQL API after module is deployed
---

> See full skill guide at `.agents/skills/09-create-content/SKILL.md`
> Agent rules at `.claude/agents/content-creator.md`

Create pages and add content to Jahia using GraphQL mutations. Use this after components have been implemented with `/implement-components`.

## Purpose

Generate working GraphQL bash scripts to create pages and content in Jahia. Scripts are saved to `$PROJECT_DIR/workflow-output/graphql-scripts/` for reuse.

**Terminology:**

- "implement" = write component code files
- "create" = add pages/content via GraphQL API

## CRITICAL PREREQUISITES

1. ✅ **ASK FOR SITE NAME** - MANDATORY, never assume (e.g., `demo`, `edc`, `mysite`)
2. ✅ **Verify components deployed** - Run `yarn build && yarn deploy` if needed
3. ✅ **Get page template name** - From `src/templates/Page/*.server.tsx` (usually `basic`)
4. ✅ **Load content data** - Read `$PROJECT_DIR/workflow-output/content-data.json` to get extracted content values

---

## 🛑 RULE 0 — NEVER SKIP IMAGES (HARD STOP)

**Image upload is NOT optional. It is the FIRST step, before any content mutation runs.**

This rule exists because skipping images was previously rationalized as "demo simplification" and produced an imageless page, defeating the purpose of the entire workflow. **Never again.**

### Hard requirements

1. **Before generating ANY content mutation script**, you MUST first generate AND execute the image upload script.
2. **Before generating ANY content mutation script**, you MUST verify that `/tmp/$SITE_NAME-images.json` exists and contains an entry for every image filename that any component will reference.
3. **A content mutation that includes a `weakreference` field is INVALID** unless its value is a UUID from `/tmp/$SITE_NAME-images.json`. Path-style references are forbidden in generated scripts.
4. **Forbidden phrases in generated scripts and prompts:** "skip image fields", "for this demo we'll skip", "images can be added later via UI", "weakreference fields skipped". If you find yourself writing these — STOP, go back to Step 0.

### The pre-flight gate (must pass before any content script runs)

Before generating content scripts, run this gate:

```bash
# 1. Count required image references in content-data.json
REQUIRED=$(python3 -c "
import json
data = json.load(open('$PROJECT_DIR/workflow-output/content-data.json'))
fields = {'image','backgroundImage','distinctionIcon','thumbnail','logo','logoImage','icon','heroImage'}
urls = set()
def walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in fields and isinstance(v, str) and (v.startswith('http') or v.startswith('/')):
                urls.add(v)
            walk(v)
    elif isinstance(obj, list):
        for x in obj: walk(x)
walk(data)
print(len(urls))
")

# 2. Verify UUID mapping file exists
[ -f /tmp/$SITE_NAME-images.json ] || { echo "GATE FAILED: no UUID mapping. Run image upload first."; exit 1; }

# 3. Verify all required images uploaded
UPLOADED=$(jq 'length' /tmp/$SITE_NAME-images.json)
echo "Required: $REQUIRED, Uploaded: $UPLOADED"
[ "$UPLOADED" -ge "$REQUIRED" ] || { echo "GATE FAILED: missing uploads"; exit 1; }
```

If the gate fails, **stop and run Step 0 first**. Do not generate or execute content scripts until it passes.

### Self-check before reporting "complete"

Before telling the user the workflow is done, verify:

```bash
# Count weakreference properties actually set on created content
SET_COUNT=$(curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
  -H 'Accept-Language: en' -H "Origin: $JAHIA_HOST" \
  -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
  --data-raw "{\"query\":\"query { jcr(workspace: EDIT) { nodesByQuery(query: \\\"select * from [jnt:content] where isdescendantnode('/sites/$SITE_NAME/home')\\\") { nodes { properties(names: [\\\"image\\\",\\\"backgroundImage\\\",\\\"thumbnail\\\",\\\"logo\\\",\\\"distinctionIcon\\\"]) { name value } } } } }\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for n in d['data']['jcr']['nodesByQuery']['nodes'] for p in n.get('properties',[]) if p.get('value')))")

echo "Image references actually set on content: $SET_COUNT (expected ≥ $REQUIRED)"
```

If `SET_COUNT < REQUIRED`, the workflow is **NOT complete** — fix it before reporting success.

---

## CRITICAL RULES (Must Follow!)

### 🚨 Rule 13: j:translation_en Nodes MUST Be Published Explicitly

**`publish(publishSubNodes: true)` does NOT include `j:translation_en` child nodes.** These are hidden system nodes that store i18n property values, and Jahia's publish API explicitly skips them.

**Symptom:** Content is visible in the Edit workspace with full text, but the LIVE page shows empty headings and labels.

**Fix — after creating ANY node with i18n properties, ALWAYS also publish its translation node:**

```bash
# After creating a content node:
curl ... --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$NODE_PATH\\\") { publish(publishSubNodes: true) } } }\"}"

# ALSO publish its translation node:
curl ... --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$NODE_PATH/j:translation_en\\\") { publish(publishSubNodes: true) } } }\"}"
```

**Required for every i18n node:** pages, content items in `/contents/`, page-area components with i18n properties, sub-pages.

**Batch helper function** to add to all scripts:
```bash
publish_with_translations() {
  local path="$1"
  curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
    -H 'Accept-Language: en' -H "Origin: $JAHIA_HOST" \
    -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$path\\\") { publish(publishSubNodes: true) } } }\"}" > /dev/null
  
  curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
    -H 'Accept-Language: en' -H "Origin: $JAHIA_HOST" \
    -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$path/j:translation_en\\\") { publish(publishSubNodes: true) } } }\"}" > /dev/null
  
  echo "Published: $path"
}

# Usage:
publish_with_translations "/sites/$SITE_NAME/home/about-us"
publish_with_translations "/sites/$SITE_NAME/contents/news/my-article"
```

### 🚨 Rule 1: Content Areas Are NOT Auto-Created

**Pages do NOT automatically create their content areas!**

**Required workflow:**

1. Create page with `jnt:page`
2. Create content area node (check template for area name - usually `main`)
3. Add components to the content area

**Hierarchy:** Page → Content Area → [Containers (optional)] → Content Components

### 🚨 Rule 2: Shell Variable Expansion

```bash
# ❌ WRONG - Single quotes prevent variable expansion
curl --data-raw '{"query": "value: \"'$VAR'\" ..."}'

# ✅ CORRECT - Double quotes with proper escaping
curl --data-raw "{\"query\": \"value: \\\"$VAR\\\" ...\"}"
```

### 🚨 Rule 3: Always Verify & Delay

```bash
RESPONSE=$(curl -s ...)
verify_response "$RESPONSE" "Operation name" || exit 1
sleep 0.5  # Wait 1-2 seconds between operations
```

**Why:** GraphQL mutations are asynchronous. No verification/delays = race conditions.

### 🚨 Rule 4: Only Request Existing Fields

```bash
# ❌ WRONG - 'path' doesn't exist on addChild
addChild(...) { uuid path }

# ✅ CORRECT
addChild(...) { uuid }
```

### 🚨 Rule 5: Required Headers

```bash
-H 'Accept-Language: en'
-H 'Origin: http://localhost:8080'
-H 'Referer: http://localhost:8080/jahia/developerTools/graphql-workspace'
-H 'accept: application/json, multipart/mixed'
-H 'content-type: application/json'
-u root:root
```

**Without Origin/Referer, requests will fail!**

### 🚨 Rule 6: Apostrophes in String Values Break JSON Silently

**Apostrophes (`'`) inside `--data-raw` double-quoted strings corrupt the JSON and cause silent failures!**

```bash
# ❌ WRONG - apostrophe becomes \' in JSON → invalid escape → malformed JSON
--data-raw "{\"query\":\"... value: \\\"we're committed\\\" ...\"}"

# ✅ CORRECT option 1 - HTML entity
--data-raw "{\"query\":\"... value: \\\"we&#39;re committed\\\" ...\"}"

# ✅ CORRECT option 2 - reword to avoid apostrophe
--data-raw "{\"query\":\"... value: \\\"we are committed\\\" ...\"}"
```

**Why insidious:** `verify_response` checks for `"errors"` in the response. When JSON is malformed, the mutation may return success-looking output but the node is NOT created (or `jq` fails with exit code 2 which `verify_response` misreads as success).

**Rule:** Before using any string in a mutation, scan for apostrophes. Replace with `&#39;` or reword.

### 🚨 Rule 7: The `@` Symbol in Richtext HTML Breaks GraphQL Parsing

**An `@` inside an HTML attribute value within `--data-raw` triggers GraphQL directive parsing!**

```bash
# ❌ WRONG - @domain.com appears as a GraphQL directive after JSON parsing
--data-raw "{\"query\":\"... value: \\\"<a href=\\\\\\\"mailto:user@domain.com\\\\\\\">text</a>\\\" ...\"}"
# Error: "Invalid syntax with offending token '@' at line 1"

# ✅ CORRECT option 1 - HTML entity for @
value: "Contact: user&#64;domain.com"

# ✅ CORRECT option 2 - strip the <a> tag, keep plain text
value: "Contact: user@domain.com"  # @ in plain text (no href) is safe
```

**Rule:** In richtext values, always encode `@` as `&#64;` inside HTML attributes (`href`, `src`, `action`), or remove the link entirely.

### 🚨 Rule 8: JCR Date Format Requires Colon in Timezone Offset

```bash
# ❌ WRONG - Jahia rejects this format
{name: "publishDate", value: "2026-02-27T00:00:00.000+0000"}
# Error: "not a valid date format: 2026-02-19T00:00:00.000+0000"

# ✅ CORRECT - colon in timezone offset is required
{name: "publishDate", value: "2026-02-27T00:00:00.000+00:00"}
```

### 🚨 Rule 9: Jahia Auto-Coerces Property Types from CND

**No need to specify `type:` for non-string properties — Jahia reads the CND definition and stores the correct type automatically.**

```bash
# ❌ UNNECESSARY - explicit type is redundant
{name: "imageOnRight", value: "false", type: BOOLEAN}
{name: "itemCount",   value: "5",     type: LONG}

# ✅ CORRECT - omit type, Jahia coerces from CND
{name: "imageOnRight", value: "false"}
{name: "itemCount",   value: "5"}
```

Only `type: WEAKREFERENCE` is required (for node references) because there is no scalar type that can be automatically inferred from the string value.

### 🚨 Rule 10: Create ALL Instances — No Subset, No Shortcuts

**The goal is pixel-perfect page recreation. Every item in `content-data.json` must be created.**

- If a carousel has 9 restaurant cards in `content-data.json`, create all 9 — not 2 "representative" examples
- If the footer has 45 country links, create all 45
- If a component has array properties (e.g., `tags: ["Chicago", "Bib Gourmand"]`), set them using the `values` field (for `multiple` string properties) or create them as individual mutations
- Cross-check: after generating scripts, count the items per section and verify against `content-data.json` counts

### 🚨 Rule 11: Set ALL Properties From content-data.json

**Every field in `content-data.json` must map to a GraphQL property. Do not skip fields.**

- If `content-data.json` has a `tags` array, set the `tags` property
- If it has `readingTimeMinutes`, set it
- If it has structured sub-objects (e.g., `navigation.primaryLinks`), create the corresponding child nodes or set the properties

Before generating a mutation, cross-reference the component's CND to ensure every non-empty field from `content-data.json` is included.

## Workflow Steps

### Step 0: Upload Images (AUTOMATIC - Run First)

Before creating content, automatically upload all required images via GraphQL:

#### 0.1. Detect Required Images

Extract image references from `workflow-output/content-data.json`:
```bash
# Find all image field values
IMAGE_FILES=$(jq -r '.componentInstances[] | .fields | to_entries[] | select(.key | test("image|Image|icon|logo"; "i")) | .value' $PROJECT_DIR/workflow-output/content-data.json | grep -E '\.(jpg|png|svg|gif)$' | sort -u)
```

#### 0.1b. Download CDN Images

If image URLs in content-data.json are remote CDN URLs (not local files in `static/assets/`), download them first:

```bash
mkdir -p /tmp/jahia-images

for img_url in $IMAGE_URLS; do
  filename=$(basename "${img_url%%\?*}")
  if [ ! -f "/tmp/jahia-images/$filename" ]; then
    echo "Downloading: $filename"
    curl -sL --user-agent "Mozilla/5.0" -o "/tmp/jahia-images/$filename" "$img_url"
  fi
done
```

Then use `/tmp/jahia-images/` as the upload source instead of `static/assets/`.

#### 0.2. Create Images Folder

```bash
# Check if images folder exists
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" \
  -H 'Accept-Language: en' -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
  --data-raw "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE_NAME/files/images\\\") { uuid } } }\"}")

# Create if missing
if echo "$RESPONSE" | grep -q '"nodeByPath":null'; then
  curl -s "$JAHIA_HOST/modules/graphql" \
    -H 'Accept-Language: en' -u "$JAHIA_USER" \
    -H "Origin: $JAHIA_HOST" -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/$SITE_NAME/files\\\") { addChild(name: \\\"images\\\", primaryNodeType: \\\"jnt:folder\\\") { uuid } } } }\"}"
fi
```

#### 0.3. Upload Images via GraphQL Multipart

> ⚠️ **CRITICAL: Write query to a temp file — NEVER pass it inline with `-F 'query=...'`**
>
> Passing the GraphQL query as an inline `-F` form field string causes ANTLR to fail with:
> `token recognition error at ''' at line 1 column 39`
>
> The only working approach in Jahia 8.2 is to write the query and variables to temp files
> and reference them with `@filename`. The REST `/files/default/` endpoint returns HTTP 405
> and is NOT supported for binary uploads in Jahia 8.2.

```bash
# Helper function for MIME type
get_mime_type() {
  case "${1##*.}" in
    jpg|jpeg) echo "image/jpeg" ;;
    png) echo "image/png" ;;
    svg) echo "image/svg+xml" ;;
    *) echo "application/octet-stream" ;;
  esac
}

# Write upload query to temp file ONCE (reused for every image)
cat > /tmp/jahia_upload_query.gql << 'GRAPHQL'
mutation uploadFile($nameInJCR: String!, $path: String!, $mimeType: String!, $fileHandle: String!) { jcr(workspace: EDIT) { addNode(name: $nameInJCR, parentPathOrId: $path, primaryNodeType: "jnt:file") { addChild(name: "jcr:content", primaryNodeType: "jnt:resource") { content: mutateProperty(name: "jcr:data") { setValue(type: BINARY, value: $fileHandle) } contentType: mutateProperty(name: "jcr:mimeType") { setValue(value: $mimeType) } } uuid } } }
GRAPHQL

# Upload each image
for img_path in static/assets/*.{jpg,png,svg,gif}; do
  [ -f "$img_path" ] || continue
  filename=$(basename "$img_path")
  mime_type=$(get_mime_type "$filename")

  # Write variables to temp file (avoids shell escaping issues)
  cat > /tmp/jahia_upload_vars.json << VARS_EOF
{"fileHandle":"fileToUpload","nameInJCR":"${filename}","path":"/sites/${SITE_NAME}/files/images","mimeType":"${mime_type}"}
VARS_EOF

  resp=$(curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H 'Accept: */*' \
    -H "Origin: $JAHIA_HOST" \
    -F "query=@/tmp/jahia_upload_query.gql" \
    -F "variables=@/tmp/jahia_upload_vars.json" \
    -F "fileToUpload=@${img_path};type=${mime_type}")

  if echo "$resp" | jq -e '.errors' > /dev/null 2>&1; then
    msg=$(echo "$resp" | jq -r '.errors[0].message' 2>/dev/null)
    if echo "$msg" | grep -q "ItemExistsException\|already exists"; then
      echo -e "${YELLOW}  SKIP: $filename already exists${NC}"
    else
      echo -e "${RED}  ERROR uploading $filename: $msg${NC}"
    fi
  else
    echo -e "${GREEN}  OK: $filename${NC}"
  fi
done
```

#### 0.4. Add jmix:image Mixin

```bash
# Query uploaded images and add mixin
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" \
  -H 'Accept-Language: en' -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
  --data-raw "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE_NAME/files/images\\\") { children(typesFilter: {types: [\\\"jnt:file\\\"]}) { nodes { uuid } } } } }\"}")

# Add jmix:image to each
echo "$RESPONSE" | jq -r '.data.jcr.nodeByPath.children.nodes[] | .uuid' | while read uuid; do
  curl -s "$JAHIA_HOST/modules/graphql" \
    -H 'Accept-Language: en' -u "$JAHIA_USER" \
    -H "Origin: $JAHIA_HOST" -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$uuid\\\") { addMixins(mixins: [\\\"jmix:image\\\"]) } } }\"}"
done
```

#### 0.5. Save UUID Mapping

```bash
# Save UUID mapping for content scripts
curl -s "$JAHIA_HOST/modules/graphql" \
  -H 'Accept-Language: en' -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
  --data-raw "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE_NAME/files/images\\\") { children(typesFilter: {types: [\\\"jnt:file\\\"]}) { nodes { uuid name path } } } } }\"}" \
  | jq '.data.jcr.nodeByPath.children.nodes' > /tmp/$SITE_NAME-images.json

# Helper function to get UUID by filename
get_image_uuid() {
  jq -r ".[] | select(.name==\"$1\") | .uuid" /tmp/$SITE_NAME-images.json
}
```

**In content scripts, use UUIDs for image properties:**
```bash
# Get UUID for image
IMAGE_UUID=$(get_image_uuid "image.jpg")

# Use in GraphQL mutation
{name: "image", value: "$IMAGE_UUID", type: WEAKREFERENCE}
```

## Pre-flight Checks (Before Creating Content)

Before generating content creation scripts, validate the site structure:

### 1. Verify Site Structure

```bash
echo "Checking site structure..."

# Check site exists
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" \
  -H 'Accept-Language: en' \
  -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" \
  -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' \
  -H 'content-type: application/json' \
  --data-raw "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE_NAME\\\") { uuid } } }\"}")

if echo "$RESPONSE" | grep -q '"nodeByPath":null'; then
  echo "✗ Site $SITE_NAME does not exist"
  exit 1
fi
echo "✓ Site exists: $SITE_NAME"

# Check home page exists
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" \
  -H 'Accept-Language: en' \
  -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" \
  -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' \
  -H 'content-type: application/json' \
  --data-raw "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE_NAME/home\\\") { uuid } } }\"}")

if echo "$RESPONSE" | grep -q '"nodeByPath":null'; then
  echo "✗ Home page does not exist"
  exit 1
fi
echo "✓ Home page exists"

# Check content area exists
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" \
  -H 'Accept-Language: en' \
  -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" \
  -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' \
  -H 'content-type: application/json' \
  --data-raw "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE_NAME/home/main\\\") { uuid } } }\"}")

if echo "$RESPONSE" | grep -q '"nodeByPath":null'; then
  echo "✗ Content area 'main' does not exist"
  exit 1
fi
echo "✓ Content area exists: main"
```

### 2. Create Files Structure

```bash
# Check files folder exists
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" \
  -H 'Accept-Language: en' \
  -u "$JAHIA_USER" \
  -H "Origin: $JAHIA_HOST" \
  -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' \
  -H 'content-type: application/json' \
  --data-raw "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE_NAME/files\\\") { uuid } } }\"}")

if echo "$RESPONSE" | grep -q '"nodeByPath":null'; then
  echo "⚠️  Files folder does not exist (unusual)"
  # Could create it, but this should exist by default
fi
echo "✓ Files folder exists"
```

**Benefits:**
- ✅ Prevents PathNotFoundException
- ✅ Clear error messages early
- ✅ Validates structure before proceeding
- ✅ More robust workflow

### Step 1.5: Create Absolute Area Content (Header and Footer)

**Absolute areas** are shared site-level components. They are created ONCE at a specific path under `/sites/{siteKey}/home/`, not in each page's `main` area.

**Check manifest for absolute-area components:**
```bash
cat workflow-output/component-manifest.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
components = data.get('components', data) if isinstance(data, dict) else data
for c in components:
    if c.get('areaType') == 'absolute':
        print(f\"{c['name']} -> area: {c.get('areaName', 'header')}\")"
```

**Create the area content node directly under `/sites/{siteKey}/home/`:**

```bash
# Example: create a siteHeader node in the header absolute area
curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
  -H 'Accept-Language: en' -H "Origin: $JAHIA_HOST" \
  -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
  -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/$SITE_NAME/home\\\") { addChild(name: \\\"header\\\", primaryNodeType: \\\"jnt:contentList\\\") { addChild(name: \\\"site-header\\\", primaryNodeType: \\\"$NS:siteHeader\\\", properties: [{name: \\\"logoAlt\\\", value: \\\"Logo\\\"}]) { uuid } } } } }\"}"

# Publish with translations
publish_with_translations "/sites/$SITE_NAME/home/header/site-header"
```

**Key rule:** The area `name` in `<AbsoluteArea name="header" ...>` must match the JCR node name you create under `/home/`. A `<AbsoluteArea name="header" parent={siteHome}>` looks for content at `/sites/{siteKey}/home/header`.

## Script Template (Use This!)

**Every generated script must follow this pattern:**

```bash
#!/bin/bash
set -e  # Exit on any error

SITE_NAME="yoursite"  # Replace with user's site name
JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

# Enhanced verification function - NEVER suppress errors
verify_response() {
  local response="$1"
  local operation="$2"

  # Check for GraphQL errors
  if echo "$response" | grep -q '"errors"'; then
    echo -e "${RED}✗ $operation${NC}"
    echo "$response" | jq '.errors[].message' 2>/dev/null || \
      echo "$response" | grep -o '"message":"[^"]*"'
    return 1
  fi

  # Check for null data
  if echo "$response" | grep -q '"data":null'; then
    echo -e "${RED}✗ $operation - No data returned${NC}"
    return 1
  fi

  echo -e "${GREEN}✓ $operation${NC}"
  return 0
}

echo "=== Creating Page ==="

# Step 1: Create page (UNIVERSAL - only j:templateName varies by project)
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
  -H 'Accept-Language: en' -H 'Origin: http://localhost:8080' \
  -H 'Referer: http://localhost:8080/jahia/developerTools/graphql-workspace' \
  -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/'$SITE_NAME'/home\") { addChild(name: \"page-name\", primaryNodeType: \"jnt:page\", properties: [{name: \"jcr:title\", value: \"Page Title\", language: \"en\"}, {name: \"j:templateName\", value: \"TEMPLATE_NAME\"}]) { uuid } } } }"}')
verify_response "$RESPONSE" "Create page" || exit 1
sleep 2

# Step 2: Create content area (check template for area name and type)
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
  -H 'Accept-Language: en' -H 'Origin: http://localhost:8080' \
  -H 'Referer: http://localhost:8080/jahia/developerTools/graphql-workspace' \
  -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/'$SITE_NAME'/home/page-name\") { addChild(name: \"AREA_NAME\", primaryNodeType: \"NAMESPACE:areaType\") { uuid } } } }"}')
verify_response "$RESPONSE" "Create content area" || exit 1
sleep 0.5

# Step 3: Add components (get types from settings/definitions.cnd)
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
  -H 'Accept-Language: en' -H 'Origin: http://localhost:8080' \
  -H 'Referer: http://localhost:8080/jahia/developerTools/graphql-workspace' \
  -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/'$SITE_NAME'/home/page-name/AREA_NAME\") { addChild(name: \"component-name\", primaryNodeType: \"NAMESPACE:componentType\", properties: [{name: \"propertyName\", value: \"Value\", language: \"en\"}]) { uuid } } } }"}')
verify_response "$RESPONSE" "Add component" || exit 1
sleep 0.5

echo -e "${GREEN}✓ Page created!${NC}"
```

**Replace these placeholders:**

- `SITE_NAME` - User's site name
- `TEMPLATE_NAME` - From template file (check `src/templates/Page/*.server.tsx`)
- `AREA_NAME` - Content area name from template (usually `main`)
- `NAMESPACE:areaType` - Content area type from template/project
- `NAMESPACE:componentType` - From component's `definition.cnd` file
- `propertyName` - From component's CND file

**Key requirements:**

- `set -e` - Exit on first error
- Sleep 2 seconds after page, 1 second between components
- Verify every response before proceeding
- Single quotes for static, double quotes when variables needed
- Only request `uuid` field
- Add `language: "en"` for i18n properties

## Using Content Data File

**IMPORTANT: Always use `$PROJECT_DIR/workflow-output/content-data.json` when available.**

### Step 1: Read Content Data

```bash
# Read the content data file
cat $PROJECT_DIR/workflow-output/content-data.json
```

### Step 2: Map Content to Components

The content data file contains:

```json
{
  "componentInstances": [
    {
      "componentType": "HeroSection",
      "instanceName": "hero",
      "order": 1,
      "contentArea": "main",
      "fields": {
        "heading": "NEW Grabbable, Snackable Ice Cream Bars!",
        "bodyText": "<p>Dessert just got handier!...</p>",
        "ctaText": "See All 5 Flavors",
        "ctaLink": "/flavors/ice-cream-bars"
      }
    }
  ]
}
```

### Step 3: Generate GraphQL Mutations

For each component instance in `componentInstances` array:

1. **Get component type**: `componentType` field (e.g., "HeroSection")
2. **Get instance name**: `instanceName` field for GraphQL `name` parameter
3. **Get content area**: `contentArea` field for parent path
4. **Get field values**: All key-value pairs in `fields` object
5. **Handle children**: If `children` array exists, create nested components

**Example mapping:**

```javascript
// From content-data.json
{
  "componentType": "HeroSection",
  "instanceName": "hero",
  "fields": {
    "heading": "Welcome",
    "bodyText": "<p>Hello world</p>"
  }
}

// Becomes GraphQL mutation
addChild(
  name: "hero",
  primaryNodeType: "namespace:heroSection",  // Get namespace from CND
  properties: [
    {name: "heading", value: "Welcome", language: "en"},
    {name: "bodyText", value: "<p>Hello world</p>", language: "en"}
  ]
)
```

### Step 4: Handle Special Field Types

**Images (weakreference):**
```json
// In content-data.json
"fields": {
  "backgroundImage": "/path/to/image.jpg"
}

// In GraphQL
properties: [
  {
    name: "backgroundImage",
    value: "/sites/$SITE_NAME/files/images/image.jpg",
    type: WEAKREFERENCE
  }
]
```

**Richtext fields:**
```json
// In content-data.json
"fields": {
  "bodyText": "<p>HTML content with <strong>formatting</strong></p>"
}

// In GraphQL (escape quotes properly)
properties: [
  {
    name: "bodyText",
    value: "<p>HTML content with <strong>formatting</strong></p>",
    language: "en"
  }
]
```

**Composite components with children:**
```json
// In content-data.json
{
  "componentType": "ContentTileGrid",
  "instanceName": "grid",
  "fields": {
    "sectionHeading": "Our Products"
  },
  "children": [
    {
      "componentType": "ContentTile",
      "instanceName": "tile-1",
      "fields": {"heading": "Product 1"}
    }
  ]
}

// Becomes multiple GraphQL mutations
// 1. Create parent grid
// 2. Create each child tile inside the grid
```

### Step 5: Order Components Correctly

Use the `order` field to create components in the correct sequence:

```bash
# Sort by order field and create in sequence
for component in componentInstances (sorted by order):
  create_component(component)
  sleep 0.5
```

## Finding Component Information

**Get component types from CND files:**

1. Open `src/components/{ComponentName}/definition.cnd` or `settings/definitions.cnd`
2. Find namespace: `<namespace = '...'>`
3. Find component definition: `[namespace:ComponentType]`
4. Note property names and check for `i18n` keyword

**Cross-reference with content-data.json:**
- Component type from CND → `primaryNodeType` in GraphQL
- Field names from CND → `fields` keys in content-data.json
- i18n flag from CND → add `language: "en"` in GraphQL

**Usage format:** `namespace:ComponentType`

**Important:**

- Component namespace ≠ site name
- Property names must match CND exactly
- i18n properties require `language: "en"`
- Non-i18n properties don't need language parameter

## Loop Pattern for Multiple Components

**When creating multiple similar components, use loops with double quotes:**

```bash
for ITEM in "Item1:Description1" "Item2:Description2"; do
  NAME=$(echo "$ITEM" | cut -d: -f1)
  DESC=$(echo "$ITEM" | cut -d: -f2)

  # CRITICAL: Use DOUBLE quotes for variable expansion
  RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
    -H 'Accept-Language: en' -H 'Origin: http://localhost:8080' \
    -H 'Referer: http://localhost:8080/jahia/developerTools/graphql-workspace' \
    -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/$SITE_NAME/home/page/area\\\") { addChild(name: \\\"item-$(echo $NAME | tr '[:upper:]' '[:lower:]')\\\", primaryNodeType: \\\"NAMESPACE:componentType\\\", properties: [{name: \\\"title\\\", value: \\\"$NAME\\\", language: \\\"en\\\"}, {name: \\\"body\\\", value: \\\"<p>$DESC</p>\\\", language: \\\"en\\\"}]) { uuid } } } }\"}")

  verify_response "$RESPONSE" "Add $NAME" || exit 1
  sleep 0.5
done
```

## Content Script Validation

After generating scripts, validate image references before execution:

### 1. Check Image Reference Format

```bash
echo "Validating image references..."

UUID_PATTERN="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ERRORS=0

# Find all WEAKREFERENCE properties in generated scripts
grep -h "type: WEAKREFERENCE" $PROJECT_DIR/workflow-output/graphql-scripts/*.sh 2>/dev/null | while read line; do
  # Extract value
  value=$(echo "$line" | grep -o 'value: "[^"]*"' | cut -d'"' -f2)

  if echo "$value" | grep -qE "$UUID_PATTERN"; then
    echo "✓ Using UUID: ${value:0:8}..."
  elif echo "$value" | grep -q "/sites/"; then
    echo "✗ ERROR: Using path instead of UUID: $value"
    ((ERRORS++))
  fi
done

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "✗ Found $ERRORS image references using paths instead of UUIDs"
  echo "  Run image upload step first to generate UUID mapping"
  exit 1
fi

echo "✓ All image references use UUIDs"
```

### 2. Verify UUID Mapping File

```bash
if [ ! -f "/tmp/$SITE_NAME-images.json" ]; then
  echo "⚠️  WARNING: No UUID mapping file found"
  echo "  Expected: /tmp/$SITE_NAME-images.json"
  echo "  Run image upload step first"
  exit 1
fi

IMAGE_COUNT=$(jq 'length' /tmp/$SITE_NAME-images.json)
echo "✓ UUID mapping file exists ($IMAGE_COUNT images)"
```

### 3. Cross-Reference Required Images

```bash
# Extract unique image filenames referenced in scripts
REQUIRED=($(grep -h "get_image_uuid" $PROJECT_DIR/workflow-output/graphql-scripts/*.sh 2>/dev/null | \
  grep -o '"[^"]*\.(jpg|png|svg|gif)"' | \
  sort -u))

echo "Checking ${#REQUIRED[@]} required images..."

MISSING=0
for img in "${REQUIRED[@]}"; do
  img_clean=$(echo "$img" | tr -d '"')
  UUID=$(jq -r ".[] | select(.name==\"$img_clean\") | .uuid" /tmp/$SITE_NAME-images.json)

  if [ -z "$UUID" ]; then
    echo "✗ Missing: $img_clean not uploaded to Jahia"
    ((MISSING++))
  fi
done

if [ $MISSING -gt 0 ]; then
  echo ""
  echo "✗ $MISSING required images not found in Jahia"
  echo "  Upload missing images first"
  exit 1
fi

echo "✓ All required images available in Jahia"
```

**Benefits:**
- ✅ Catches UUID/path issues early
- ✅ Verifies images uploaded
- ✅ Clear error messages before execution
- ✅ Prevents runtime failures

## Image Upload Workflow

**CRITICAL: Images must be uploaded BEFORE creating components that reference them.**

### Complete Image Upload Process

**Step 1: Extract images from content-data.json**

Read the `extractedImages` array from `workflow-output/content-data.json`:

```json
{
  "extractedImages": [
    {
      "originalUrl": "https://example.com/images/hero.jpg",
      "localPath": "/tmp/website-download/example.com/images/hero.jpg",
      "type": "hero-background",
      "usedBy": ["HeroSection"]
    }
  ]
}
```

**Step 2: Create images folder structure**

Create the necessary folder structure in Jahia using GraphQL:

```bash
# Create main images folder
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
  -H 'Accept-Language: en' \
  -H 'Origin: http://localhost:8080' \
  -H 'Referer: http://localhost:8080/jahia/developerTools/graphql-workspace' \
  -H 'accept: application/json, multipart/mixed' \
  -H 'content-type: application/json' \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/'$SITE_NAME'/files\") { addChild(name: \"images\", primaryNodeType: \"jnt:folder\") { uuid } } } }"}')
verify_response "$RESPONSE" "Create images folder" || exit 1
sleep 1

# Optional: Create subfolders for organization (hero, banners, tiles, etc.)
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
  -H 'Accept-Language: en' \
  -H 'Origin: http://localhost:8080' \
  -H 'Referer: http://localhost:8080/jahia/developerTools/graphql-workspace' \
  -H 'accept: application/json, multipart/mixed' \
  -H 'content-type: application/json' \
  --data-raw '{"query":"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \"/sites/'$SITE_NAME'/files/images\") { addChild(name: \"hero\", primaryNodeType: \"jnt:folder\") { uuid } } } }"}')
verify_response "$RESPONSE" "Create hero images folder" || exit 1
sleep 0.5
```

**Step 3: Upload images via GraphQL Multipart**

> ⚠️ **The REST endpoint `/files/default/` returns HTTP 405 in Jahia 8.2. Use GraphQL multipart.**

Use the `@file` form field approach (see section 0.3 above):

```bash
# Write upload query to temp file ONCE
cat > /tmp/jahia_upload_query.gql << 'GRAPHQL'
mutation uploadFile($nameInJCR: String!, $path: String!, $mimeType: String!, $fileHandle: String!) { jcr(workspace: EDIT) { addNode(name: $nameInJCR, parentPathOrId: $path, primaryNodeType: "jnt:file") { addChild(name: "jcr:content", primaryNodeType: "jnt:resource") { content: mutateProperty(name: "jcr:data") { setValue(type: BINARY, value: $fileHandle) } contentType: mutateProperty(name: "jcr:mimeType") { setValue(value: $mimeType) } } uuid } } }
GRAPHQL

# Loop through all images
for IMAGE_PATH in /tmp/website-download/example.com/images/*.jpg; do
  IMAGE_NAME=$(basename "$IMAGE_PATH")
  MIME_TYPE="image/jpeg"  # Adjust per file extension

  echo "Uploading: $IMAGE_NAME"

  cat > /tmp/jahia_upload_vars.json << VARS_EOF
{"fileHandle":"fileToUpload","nameInJCR":"${IMAGE_NAME}","path":"/sites/${SITE_NAME}/files/images","mimeType":"${MIME_TYPE}"}
VARS_EOF

  curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
    -H 'Accept: */*' \
    -H "Origin: $JAHIA_HOST" \
    -F "query=@/tmp/jahia_upload_query.gql" \
    -F "variables=@/tmp/jahia_upload_vars.json" \
    -F "fileToUpload=@${IMAGE_PATH};type=${MIME_TYPE}"

  sleep 0.5
done
```

**Step 4: Build image path mapping**

Create a mapping of local image paths to Jahia paths:

```bash
# Example: Map local paths to Jahia paths
declare -A IMAGE_MAP

# From content-data.json localPath → Jahia path
IMAGE_MAP["/tmp/website-download/example.com/images/hero.jpg"]="/sites/$SITE_NAME/files/images/hero.jpg"
IMAGE_MAP["/path/to/tile-image-1.jpg"]="/sites/$SITE_NAME/files/images/tile-image-1.jpg"
```

**Step 5: Use image paths in component creation**

When creating components, reference uploaded images with `type: WEAKREFERENCE`:

```bash
# Extract image path from content-data.json field
IMAGE_FIELD_VALUE="/path/to/tile-image-1.jpg"

# Map to Jahia path
JAHIA_IMAGE_PATH="${IMAGE_MAP[$IMAGE_FIELD_VALUE]}"

# Use in GraphQL mutation
RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
  -H 'Accept-Language: en' \
  -H 'Origin: http://localhost:8080' \
  -H 'Referer: http://localhost:8080/jahia/developerTools/graphql-workspace' \
  -H 'accept: application/json, multipart/mixed' \
  -H 'content-type: application/json' \
  --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/$SITE_NAME/home/page/area\\\") { addChild(name: \\\"component-name\\\", primaryNodeType: \\\"namespace:componentType\\\", properties: [{name: \\\"image\\\", value: \\\"$JAHIA_IMAGE_PATH\\\", type: WEAKREFERENCE}, {name: \\\"heading\\\", value: \\\"Component Title\\\", language: \\\"en\\\"}]) { uuid } } } }\"}")
verify_response "$RESPONSE" "Create component with image" || exit 1
```

### Complete Image Upload Script Pattern

**Generate a dedicated image upload script (`01-upload-images.sh`) that runs first:**

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGES_DIR="$SCRIPT_DIR/../../static/assets"
SITE="yoursite"
JAHIA_HOST="http://localhost:8080"
JAHIA_AUTH="root:root"
IMAGES_JSON="/tmp/${SITE}-images.json"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'

verify_response() {
  local response="$1"
  local context="$2"
  if echo "$response" | jq -e '.errors' > /dev/null 2>&1; then
    echo -e "${RED}ERROR in $context:${NC}"
    echo "$response" | jq '.errors'
    return 1
  fi
  echo -e "${GREEN}OK: $context${NC}"
  return 0
}

gql() {
  curl -s "$JAHIA_HOST/modules/graphql" \
    -H "Accept-Language: en" \
    -H "Origin: $JAHIA_HOST" \
    -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H "accept: application/json, multipart/mixed" \
    -H "content-type: application/json" \
    -u "$JAHIA_AUTH" \
    --data-raw "$1"
}

echo "=== Uploading Images ==="

# Create images folder (ignore error if already exists)
FOLDER_RESP=$(gql "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/$SITE/files\\\") { addChild(name: \\\"images\\\", primaryNodeType: \\\"jnt:folder\\\") { uuid } } } }\"}")
if echo "$FOLDER_RESP" | jq -e '.errors' > /dev/null 2>&1; then
  echo -e "${YELLOW}Folder may already exist, continuing...${NC}"
else
  echo -e "${GREEN}OK: images folder created${NC}"
fi
sleep 0.5

# Write upload query to temp file ONCE
# NOTE: Must use @file approach — inline -F 'query=...' causes ANTLR token recognition errors
cat > /tmp/jahia_upload_query.gql << 'GRAPHQL'
mutation uploadFile($nameInJCR: String!, $path: String!, $mimeType: String!, $fileHandle: String!) { jcr(workspace: EDIT) { addNode(name: $nameInJCR, parentPathOrId: $path, primaryNodeType: "jnt:file") { addChild(name: "jcr:content", primaryNodeType: "jnt:resource") { content: mutateProperty(name: "jcr:data") { setValue(type: BINARY, value: $fileHandle) } contentType: mutateProperty(name: "jcr:mimeType") { setValue(value: $mimeType) } } uuid } } }
GRAPHQL

get_mime_type() {
  case "${1##*.}" in
    jpg|jpeg) echo "image/jpeg" ;;
    png)      echo "image/png" ;;
    svg)      echo "image/svg+xml" ;;
    gif)      echo "image/gif" ;;
    webp)     echo "image/webp" ;;
    *)        echo "application/octet-stream" ;;
  esac
}

upload_image() {
  local filename="$1"
  local filepath="$IMAGES_DIR/$filename"
  local mime=$(get_mime_type "$filename")

  if [ ! -f "$filepath" ]; then
    echo -e "${RED}  WARNING: File not found: $filepath${NC}"
    return 1
  fi

  cat > /tmp/jahia_upload_vars.json << VARS_EOF
{"fileHandle":"fileToUpload","nameInJCR":"${filename}","path":"/sites/${SITE}/files/images","mimeType":"${mime}"}
VARS_EOF

  local resp
  resp=$(curl -s -u "$JAHIA_AUTH" "$JAHIA_HOST/modules/graphql" \
    -H 'Accept: */*' \
    -H "Origin: $JAHIA_HOST" \
    -F "query=@/tmp/jahia_upload_query.gql" \
    -F "variables=@/tmp/jahia_upload_vars.json" \
    -F "fileToUpload=@${filepath};type=${mime}")

  if echo "$resp" | jq -e '.errors' > /dev/null 2>&1; then
    local msg
    msg=$(echo "$resp" | jq -r '.errors[0].message' 2>/dev/null)
    if echo "$msg" | grep -q "ItemExistsException\|already exists"; then
      echo -e "${YELLOW}  SKIP: $filename already exists${NC}"
      return 0
    fi
    echo -e "${RED}  ERROR uploading $filename: $msg${NC}"
    return 1
  fi
  echo -e "${GREEN}  OK: $filename${NC}"
}

# Upload all images from static/assets/
echo "Uploading images from $IMAGES_DIR..."
for img_path in "$IMAGES_DIR"/*.{jpg,jpeg,png,svg,gif,webp}; do
  [ -f "$img_path" ] || continue
  img_name=$(basename "$img_path")
  echo "  Uploading: $img_name"
  upload_image "$img_name" || true
  sleep 0.3
done

# Add jmix:image mixin to all uploaded files
echo ""
echo "Adding jmix:image mixin..."
UUID_LIST=$(gql "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE/files/images\\\") { children(typesFilter: {types: [\\\"jnt:file\\\"]}) { nodes { uuid name } } } } }\"}")
echo "$UUID_LIST" | jq -r '.data.jcr.nodeByPath.children.nodes[] | .uuid' | while read uuid; do
  MIXIN_RESP=$(gql "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$uuid\\\") { addMixins(mixins: [\\\"jmix:image\\\"]) } } }\"}")
  if echo "$MIXIN_RESP" | jq -e '.errors' > /dev/null 2>&1; then
    echo -e "${RED}  WARNING: Could not add mixin to $uuid${NC}"
  fi
  sleep 0.2
done

# Save UUID mapping
echo ""
echo "Saving UUID mapping to $IMAGES_JSON..."
UUID_RESP=$(gql "{\"query\":\"query { jcr(workspace: EDIT) { nodeByPath(path: \\\"/sites/$SITE/files/images\\\") { children(typesFilter: {types: [\\\"jnt:file\\\"]}) { nodes { uuid name } } } } }\"}")
verify_response "$UUID_RESP" "Query image UUIDs"
echo "$UUID_RESP" | jq '.data.jcr.nodeByPath.children.nodes' > "$IMAGES_JSON"
echo -e "${GREEN}UUID mapping saved to $IMAGES_JSON${NC}"

echo ""
echo -e "${GREEN}=== Image Upload COMPLETE ===${NC}"
```

### Image Reference Format

> ✅ **Use UUID or path** — Jahia accepts both for WEAKREFERENCE, but UUID is more stable.

**For single images (using UUID from upload mapping):**
```bash
# Get UUID from mapping file saved during upload
IMAGE_UUID=$(jq -r ".[] | select(.name==\"hero.jpg\") | .uuid" /tmp/$SITE-images.json)

properties: [{
  name: "heroImage",
  value: "$IMAGE_UUID",
  type: WEAKREFERENCE
}]
```

**Alternative: use path directly (also works):**
```bash
properties: [{
  name: "heroImage",
  value: "/sites/$SITE_NAME/files/images/hero.jpg",
  type: WEAKREFERENCE
}]
```

**For responsive images (mobile + desktop):**
```bash
properties: [
  {
    name: "backgroundImageMobile",
    value: "/sites/$SITE_NAME/files/images/hero-mobile.jpg",
    type: WEAKREFERENCE
  },
  {
    name: "backgroundImageDesktop",
    value: "/sites/$SITE_NAME/files/images/hero-desktop.jpg",
    type: WEAKREFERENCE
  }
]
```

### Execution Order

**The correct script execution order is:**

1. `00-upload-images.sh` - Upload all images first
2. `01-create-homepage.sh` - Create page structure
3. `02-add-hero-section.sh` - Add hero (references uploaded images)
4. `03-add-content-grid.sh` - Add grid components (references uploaded images)
5. ... additional component scripts ...

**NEVER create components with image references before uploading the images!**

### Step 6: Create Sub-Page Content

Each sub-page may have its own components. Read `content-data.json` for page-specific component instances and create them in each page's `main` area.

**content-data.json structure for sub-pages** (expected format):
```json
{
  "pages": {
    "about-us": {
      "title": "About Us",
      "template": "basic",
      "components": [
        {
          "componentType": "namespace:textSection",
          "nodeName": "intro-text",
          "contentPlacement": "pageArea",
          "fields": { "title": "About Credit Agricole CIB", "body": "..." }
        }
      ]
    }
  }
}
```

**Create content area for each sub-page, then add components:**
```bash
for PAGE in about-us our-services expertise news; do
  # Create the main content area
  curl -s "$JAHIA_HOST/modules/graphql" -u "$JAHIA_USER" \
    -H 'Accept-Language: en' -H "Origin: $JAHIA_HOST" \
    -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H 'accept: application/json, multipart/mixed' -H 'content-type: application/json' \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"/sites/$SITE_NAME/home/$PAGE\\\") { addChild(name: \\\"main\\\", primaryNodeType: \\\"jnt:contentList\\\") { uuid } } } }\"}" > /dev/null
  
  echo "Created main area for $PAGE"
done

# Then for each page, add its components from content-data.json
# (Read the pages[pageName].components array and create each as a child of /sites/.../home/{page}/main)
```

**If `content-data.json` has no `pages` section**, the sub-pages will have empty content areas. This is acceptable for a demo — editors can add content via jContent UI. Document this in the final report.

## Generate Cleanup Script

After generating content creation scripts, automatically generate a cleanup utility:

```bash
# Generate 99-cleanup-all-content.sh

cat > $PROJECT_DIR/workflow-output/graphql-scripts/99-cleanup-all-content.sh << 'EOF'
#!/bin/bash

SITE_NAME="SITE_NAME_PLACEHOLDER"
JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║                                                        ║${NC}"
echo -e "${YELLOW}║  ⚠️  WARNING: This will delete ALL homepage content  ║${NC}"
echo -e "${YELLOW}║                                                        ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to cancel, or Enter to continue...${NC}"
read

echo "Deleting content..."

# Delete all created nodes in reverse order
NODES=(
  # List populated from created nodes during generation
  CLEANUP_NODES_PLACEHOLDER
)

for node in "${NODES[@]}"; do
  echo -n "  Deleting: $(basename $node)... "

  RESPONSE=$(curl -s "$JAHIA_HOST/modules/graphql" \
    -H 'Accept-Language: en' \
    -u "$JAHIA_USER" \
    -H "Origin: $JAHIA_HOST" \
    -H "Referer: $JAHIA_HOST/jahia/developerTools/graphql-workspace" \
    -H 'accept: application/json, multipart/mixed' \
    -H 'content-type: application/json' \
    --data-raw "{\"query\":\"mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: \\\"$node\\\") { delete } } }\"}")

  if echo "$RESPONSE" | grep -q '"errors"'; then
    # Check if it's just "doesn't exist" error
    if echo "$RESPONSE" | grep -q "PathNotFoundException"; then
      echo -e "${YELLOW}⊘${NC} (already deleted)"
    else
      echo -e "${RED}✗${NC}"
    fi
  else
    echo -e "${GREEN}✓${NC}"
  fi
done

echo ""
echo -e "${GREEN}✓ Cleanup complete${NC}"
EOF

chmod +x $PROJECT_DIR/workflow-output/graphql-scripts/99-cleanup-all-content.sh
```

**Track created nodes during script generation:**

```bash
# Initialize cleanup nodes array
CLEANUP_NODES=()

# As each content script is generated, add its node paths to CLEANUP_NODES array
# Example during component creation:
CLEANUP_NODES+=("/sites/$SITE_NAME/home/main/$NODE_NAME")

# After all scripts generated, replace placeholders in cleanup script
# Replace site name
sed -i "s|SITE_NAME_PLACEHOLDER|$SITE_NAME|" \
  $PROJECT_DIR/workflow-output/graphql-scripts/99-cleanup-all-content.sh

# Replace nodes list (in reverse order for proper deletion)
REVERSED_NODES=$(printf '  "%s"\n' "${CLEANUP_NODES[@]}" | tac)
sed -i "s|CLEANUP_NODES_PLACEHOLDER|$REVERSED_NODES|" \
  $PROJECT_DIR/workflow-output/graphql-scripts/99-cleanup-all-content.sh

echo "✓ Cleanup script generated: 99-cleanup-all-content.sh"
```

**Benefits:**
- ✅ Easy testing iteration - quickly reset content
- ✅ Safe with confirmation prompt
- ✅ Handles non-existent nodes gracefully
- ✅ Deletes in reverse order to avoid constraint violations

## Generate Master Orchestration Script

Generate `00-run-all.sh` to execute the complete workflow with progress tracking:

```bash
cat > $PROJECT_DIR/workflow-output/graphql-scripts/00-run-all.sh << 'EOF'
#!/bin/bash
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                        ║${NC}"
echo -e "${BLUE}║     Complete Content Creation Workflow                ║${NC}"
echo -e "${BLUE}║                                                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Steps with descriptions
STEPS=(
  "00-create-images-folder.sh:Creating images folder"
  "00-upload-images-graphql.sh:Uploading images via GraphQL"
  "00-add-image-mixin.sh:Adding jmix:image to images"
  "00-check-images.sh:Verifying image upload"
  CONTENT_SCRIPTS_PLACEHOLDER
)

SUCCESS=0
FAILED=0
TOTAL=${#STEPS[@]}

for step in "${STEPS[@]}"; do
  SCRIPT="${step%%:*}"
  DESCRIPTION="${step##*:}"
  CURRENT=$((SUCCESS + FAILED + 1))

  echo ""
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}Step $CURRENT/$TOTAL: $DESCRIPTION${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

  if [ ! -f "$SCRIPT" ]; then
    echo -e "${RED}✗ Script not found: $SCRIPT${NC}"
    ((FAILED++))
    continue
  fi

  if bash "$SCRIPT"; then
    ((SUCCESS++))
    echo -e "${GREEN}✓ Completed: $DESCRIPTION${NC}"
  else
    ((FAILED++))
    echo -e "${RED}✗ Failed: $DESCRIPTION${NC}"
    echo ""
    echo "To resume from this point, run:"
    echo "  bash $SCRIPT"
    echo ""
    echo "Summary so far:"
    echo "  Success: $SUCCESS"
    echo "  Failed: $FAILED"
    exit 1
  fi

  sleep 1
done

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                        ║${NC}"
echo -e "${GREEN}║              Workflow Complete!                        ║${NC}"
echo -e "${GREEN}║                                                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Summary:"
echo "  Total steps: $TOTAL"
echo "  Success: $SUCCESS"
echo "  Failed: $FAILED"
echo ""
echo "View your page:"
echo "  http://localhost:8080/cms/edit/default/en/sites/SITE_NAME_PLACEHOLDER/home.html"
echo ""
EOF

chmod +x $PROJECT_DIR/workflow-output/graphql-scripts/00-run-all.sh

# Add all content scripts to STEPS array
CONTENT_SCRIPTS=($(ls $PROJECT_DIR/workflow-output/graphql-scripts/*.sh 2>/dev/null | grep -E "[0-9]{2}-" | grep -v "^00-" | sort))
SCRIPT_LINES=""
for script in "${CONTENT_SCRIPTS[@]}"; do
  name=$(basename "$script")
  desc=$(grep "^echo \"===" "$script" 2>/dev/null | head -1 | sed 's/echo "=== //; s/ ===//; s/"$//' || echo "Content creation")
  SCRIPT_LINES="${SCRIPT_LINES}  \"$name:$desc\"\n"
done

# Replace placeholders
sed -i "s|CONTENT_SCRIPTS_PLACEHOLDER|$SCRIPT_LINES|" \
  $PROJECT_DIR/workflow-output/graphql-scripts/00-run-all.sh

sed -i "s|SITE_NAME_PLACEHOLDER|$SITE_NAME|" \
  $PROJECT_DIR/workflow-output/graphql-scripts/00-run-all.sh

echo "✓ Master script generated: 00-run-all.sh"
echo ""
echo "Usage:"
echo "  cd $PROJECT_DIR/workflow-output/graphql-scripts"
echo "  ./00-run-all.sh"
```

**Benefits:**
- ✅ Single command execution
- ✅ Progress tracking with step numbers
- ✅ Resume capability with clear instructions
- ✅ Colored output for better visibility
- ✅ Clear summary at completion

## Output Organization

**All scripts and files saved to `$PROJECT_DIR/workflow-output/`:**

- `$PROJECT_DIR/workflow-output/graphql-scripts/00-upload-images.sh` - Image upload script (runs first)
- `$PROJECT_DIR/workflow-output/graphql-scripts/01-create-homepage.sh` - Homepage creation script
- `$PROJECT_DIR/workflow-output/graphql-scripts/02-*.sh` - Component creation scripts (numbered by order)
- `$PROJECT_DIR/workflow-output/graphql-scripts/00-run-all.sh` - Master orchestration script
- `$PROJECT_DIR/workflow-output/graphql-scripts/99-cleanup-all-content.sh` - Cleanup utility
- `$PROJECT_DIR/workflow-output/content-data.json` - Extracted content data from website

## Complete Workflow Process

When `/create-content` is invoked, follow this exact sequence:

### Phase 1: Preparation

0. **Determine project directory** (`PROJECT_DIR`):
   - Check if `settings/definitions.cnd` exists in current directory → `PROJECT_DIR="."`
   - Otherwise run `find . -name "definitions.cnd" -path "*/settings/*" | head -1` and use its grandparent
   - If ambiguous (multiple projects), ask the user which project to use

1. **Load content data**: Read `$PROJECT_DIR/workflow-output/content-data.json`

2. **Audit content data completeness**: Build a summary table:

   | Component Type | Instances | Children | Fields per Instance |
   |---------------|-----------|----------|---------------------|

   Cross-reference against component CND definitions:
   - Every component type in the project must have ≥1 instance
   - Every container component must have ≥1 child (warn if 0)
   - Every i18n field must have a value in content-data.json

   If any container has 0 children, **warn the user** — this likely indicates incomplete analysis. Ask whether to proceed or re-run `/analyze-website`.

3. **Ask for site name**: Prompt user for Jahia site name
4. **Verify prerequisites**:
   - Check components are deployed (`yarn build && yarn deploy`)
   - Get template name from `src/templates/Page/*.server.tsx`
5. **Enumerate required images**: Walk the entire content-data.json (recursively, including nested `children` arrays). Collect every value where the field name is one of `image`, `backgroundImage`, `distinctionIcon`, `thumbnail`, `logo`, `logoImage`, `icon`, `heroImage`. Build a `(node_path, field_name, url, target_filename)` mapping. **Total count = N.** Report N to the user before proceeding.

### Phase 1.5: Image Upload (BLOCKING — must complete before Phase 2)

This phase is non-skippable. If `N > 0`, you MUST execute every step below before generating any content script.

1. **Download** all `N` URLs to `/tmp/jahia-images/` (curl with browser User-Agent, skip cached files)
2. **Verify** every download succeeded — file exists, size > 100 bytes
3. **Create** `/sites/$SITE_NAME/files/images` folder in Jahia (ignore ItemExistsException)
4. **Write** the upload query to `/tmp/jahia_upload_query.gql` (must use `@file` form, never inline)
5. **Upload** each image via `curl -F "query=@..." -F "variables=@..." -F "fileToUpload=@..."` — verify each response has `"uuid"` and no `"errors"`
6. **Add `jmix:image` mixin** to every uploaded file
7. **Save UUID mapping** to `/tmp/$SITE_NAME-images.json` — verify it has ≥ N entries
8. **GATE CHECK** (Rule 0 above): assert `jq 'length' /tmp/$SITE_NAME-images.json` ≥ N. If it fails, STOP and fix uploads — do not proceed.

Persist the `(node_path, field, uuid)` mapping for use in Phase 2/3.

### Phase 2: Generate Scripts

**Image field handling (CRITICAL):**
Before generating a mutation for any component, check its CND definition:
- If a field is `(weakreference, picker[type='image'])`: the value in content-data.json is a URL that must be uploaded to Jahia first. Use the UUID from the upload mapping with `type: WEAKREFERENCE`.
- If a field is `(string)`: use the value directly as-is (no upload needed).

Never pass a raw URL as a WEAKREFERENCE value — it will fail. Always upload first, then use the UUID or JCR path.

1. **Generate `00-upload-images.sh`**:
   - Create images folder structure in Jahia
   - Upload all images from `static/assets/images/` or `/tmp/website-download/`
   - Build image path mapping (local path → Jahia path)

2. **Generate `01-create-homepage.sh`**:
   - Create page with proper template
   - Create content area(s)

3. **Generate component scripts (`02-*.sh`, `03-*.sh`, etc.)**:
   - For each component in `componentInstances` (sorted by `order`)
   - Map `fields` to GraphQL properties
   - Map image fields to uploaded Jahia paths using `type: WEAKREFERENCE`
   - Handle nested `children` components

### Phase 2.1: Post-Generation Verification

After generating all scripts, run these counts and refuse to proceed if any fails:

| Check | Required | Actual |
|-------|----------|--------|
| Content mutations match items in content-data.json | = | |
| Image WEAKREFERENCE values are UUIDs (not paths, not URLs) | 100% | |
| Generated scripts contain zero occurrences of "skip image" / "TODO" / "for this demo" | 0 | |
| Every weakreference field referenced in content-data.json has a UUID in `/tmp/$SITE_NAME-images.json` | 100% | |

Run this validation programmatically:
```bash
# Forbidden phrases in any generated script
if grep -irE "skip.{0,20}image|images.{0,30}skipped|for this demo|TODO.*image" $PROJECT_DIR/workflow-output/graphql-scripts/; then
  echo "FAIL: forbidden phrases found in generated scripts"; exit 1
fi

# Every weakreference value must be a UUID, not a URL or path
if grep -h "type:.*WEAKREFERENCE" $PROJECT_DIR/workflow-output/graphql-scripts/*.sh | grep -E 'value:.*"(http|/sites/)'; then
  echo "FAIL: weakreference values contain URLs or paths"; exit 1
fi
```

### Phase 3: Save and Execute

1. **Save all scripts** to `$PROJECT_DIR/workflow-output/graphql-scripts/`
2. **Generate master script** `00-run-all.sh` with correct execution order — **must put image upload FIRST**
3. **Execute scripts** in order. After execution, run the Rule 0 self-check (count weakreference properties actually set on content). If `SET_COUNT < N`, the workflow is incomplete — fix and re-run.

## Usage

```bash
/create-content
```

**The command will automatically:**
- Read `$PROJECT_DIR/workflow-output/content-data.json` if it exists
- Extract all content values and image references
- Generate complete bash scripts including image upload
- Create proper image mappings for WEAKREFERENCE properties
- Ask for site name before generating scripts

**If content-data.json is not found:**
- Prompt user to provide page and content specifications manually

## After Creation

After completion, you'll receive:

- **Generated scripts** in `$PROJECT_DIR/workflow-output/graphql-scripts/`
  - `00-upload-images.sh` - Upload all images
  - `01-create-homepage.sh` - Create page structure
  - `02-*.sh` through `0X-*.sh` - Create components with content
  - `00-run-all.sh` - Master script to run everything
- **Page URLs** for verification in Jahia
- **Summary report** of created content
- **Instructions** for:
  - Running the scripts
  - Publishing content in Jahia UI
  - Verifying image uploads

**To execute the scripts:**

```bash
cd $PROJECT_DIR/workflow-output/graphql-scripts
bash 00-run-all.sh
```

Or run individually for testing:
```bash
bash 00-upload-images.sh
bash 01-create-homepage.sh
bash 02-add-hero-section.sh
```

## Workflow Context

This is typically the **fifth step** in the complete Jahia workflow:

1. **`/analyze-website`** - Analyze website, identify components, **extract content data**
2. **`/import-website-assets`** - Import CSS, JS, images, fonts to `static/` folder
3. **`/implement-components`** - Generate component code (CND, TSX, CSS)
4. **Build & Deploy** - `yarn build && yarn deploy`
5. **`/create-content`** - Upload images and create pages with extracted content ← You are here
6. **Publish** - Publish content to LIVE in Jahia UI

**Key improvements:**
- **Automated image upload**: `00-upload-images.sh` uploads all images before content creation
- **Content data integration**: Uses `content-data.json` for accurate content population
- **Proper execution order**: Images → Page → Components (in order)

Or run the complete workflow with: `/jahia-workflow`
