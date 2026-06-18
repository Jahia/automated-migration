---
name: 9-create-content
description: Create pages and content nodes via the Jahia MCP server. Always prefer MCP over GraphQL for all content operations. Publishes all nodes after creation. Use after page templates are deployed.
type: content
phase: 9
status: active
depends_on:
  - 8-page-templates
allowed-tools: Bash, Read, WebFetch
---

# Skill: Create Content

Creates content nodes in a running Jahia instance using the **Jahia MCP server**, then publishes them.

---

## Agent identity
- **Agent name:** Datacraft
- **Reference style:** Data engineering / ETL
- **Signature line (en):** *"The API is the content layer."*
- **Personality note:** Systematic about publication order. Always publishes after every mutation. Never leaves nodes in draft state.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## MCP-first rule (non-negotiable)

**Always use the Jahia MCP server for ALL content operations. Never use GraphQL mutations for content management.**

The MCP server at `http://localhost:8080/modules/mcp` provides purpose-built tools for every content operation. MCP calls are:
- Simpler: no hand-crafted GraphQL strings
- Safer: typed inputs, server-side validation
- More complete: media upload, publication, page structure discovery all in one place

**MCP availability check (run at start of every session):**
```bash
curl -s http://localhost:8080/modules/mcp | python3 -c "import json,sys; d=json.load(sys.stdin); print('MCP OK -', d['version'], '-', len(d['tools']), 'tools')"
```

Expected: `MCP OK - 0.5.0-SNAPSHOT - 31 tools`

If MCP is unavailable (connection refused, 404, or 0 tools), fall back to GraphQL and note it in the session log.

---

## MCP call pattern

All MCP calls use JSON-RPC 2.0 over HTTP POST:

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "TOOL_NAME",
      "arguments": { ... }
    }
  }' | python3 -m json.tool
```

---

## MCP tool reference

### Discover what is available on a page before adding content

```bash
# What areas and allowed types does this page have?
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"page.structure","arguments":{"path":"/sites/SITEKEY/home/my-page"}}}' \
  | python3 -m json.tool
```

```bash
# What properties does a content type have?
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"content.type","arguments":{"nodeType":"sialp:pageHero"}}}' \
  | python3 -m json.tool
```

### Create a page

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"page.create","arguments":{
      "parentPath": "/sites/SITEKEY/home",
      "name": "sial-innovation",
      "title": "SIAL Innovation",
      "templateName": "basic",
      "locale": "fr"
    }}
  }' | python3 -m json.tool
```

### Create a content node (with properties and children in one call)

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.create","arguments":{
      "parentPath": "/sites/SITEKEY/home/sial-innovation/main",
      "nodeType": "sialp:pageHero",
      "locale": "fr",
      "properties": {
        "jcr:title": "SIAL Innovation",
        "subtitle": "Tendances & Innovations Alimentaires",
        "backgroundImageUrl": "http://localhost:8080/files/live/sites/SITEKEY/files/imported-images/heroes/sial-innovation-hero.jpg"
      }
    }}
  }' | python3 -m json.tool
```

**Property rules:**
- i18n and non-i18n properties are both passed in the same `properties` map — the MCP resolves i18n automatically using the `locale` param
- WEAKREFERENCE properties accept a UUID **or** an absolute JCR path — use the path when you have it
- Multi-valued: use a JSON array `["value1", "value2"]`
- Dates: ISO-8601 `"2026-06-01T00:00:00.000Z"`

### Create a node with children in one atomic call

Use `children` to create a container and its items in one shot (e.g. a push cards section with its 4 cards):

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.create","arguments":{
      "parentPath": "/sites/SITEKEY/home/sial-innovation/main",
      "nodeType": "sialp:pagesPushes",
      "locale": "fr",
      "properties": {
        "heading": "Découvrir SIAL Innovation"
      },
      "children": [
        {
          "nodeType": "sialp:pagesPushesItem",
          "name": "le-jury",
          "properties": {
            "jcr:title": "LE JURY",
            "description": "Découvrez les membres du jury",
            "imageExternalUrl": "http://localhost:8080/files/live/sites/SITEKEY/files/imported-images/jury.jpg"
          }
        },
        {
          "nodeType": "sialp:pagesPushesItem",
          "name": "palmares-2024",
          "properties": {
            "jcr:title": "PALMARÈS 2024",
            "description": "Les lauréats de l édition 2024"
          }
        }
      ]
    }}
  }' | python3 -m json.tool
```

### Update an existing node

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.update","arguments":{
      "path": "/sites/SITEKEY/home/main/hero",
      "locale": "fr",
      "properties": {
        "backgroundImageUrl": "http://localhost:8080/files/live/sites/SITEKEY/files/imported-images/heroes/home-hero.jpg"
      }
    }}
  }' | python3 -m json.tool
```

### Delete a node

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.mark_for_deletion","arguments":{
      "path": "/sites/SITEKEY/home/my-page/main/old-hero"
    }}
  }' | python3 -m json.tool
```

Note: `content.delete` only works on draft-only nodes. Use `content.mark_for_deletion` for published nodes, then `publication.unpublish` + `content.delete` if hard delete is needed.

### Upload an image from a remote URL (replaces image proxy for most cases)

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"media.upload.url","arguments":{
      "siteKey": "SITEKEY",
      "sourceUrl": "https://www.sialparis.com/-/media/Project/.../banner/hero.jpg",
      "folder": "imported-images/heroes",
      "fileName": "sial-innovation-hero.jpg",
      "mimeType": "image/jpeg"
    }}
  }' | python3 -m json.tool
```

The response contains the JCR path and UUID of the uploaded file. Use the path directly as a property value (WEAKREFERENCE accepts absolute JCR path).

**Use `media.upload.url` instead of the image proxy whenever the source URL is directly accessible.** The image proxy (`/modules/jahia-image-proxy/import-image`) remains available as a fallback when `media.upload.url` fails (e.g. CDN requires specific headers).

### Upload a local file (binary upload)

```bash
# Step 1 - create upload ticket
TICKET=$(curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"media.upload.create","arguments":{
      "siteKey": "SITEKEY",
      "folder": "imported-images",
      "fileName": "hero.jpg",
      "mimeType": "image/jpeg",
      "sizeBytes": 204800
    }}
  }')

UPLOAD_URL=$(echo $TICKET | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['result']['content'][0]['text'])" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['uploadUrl'])")
TOKEN=$(echo $TICKET | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['result']['content'][0]['text'])" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['token'])")

# Step 2 - PUT the file
curl -s -X PUT "$UPLOAD_URL" -H "Content-Type: image/jpeg" --data-binary @/tmp/hero.jpg

# Step 3 - finalize
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"media.upload.finalize\",\"arguments\":{\"token\":\"$TOKEN\"}}}" \
  | python3 -m json.tool
```

### Publish a node (and optionally its subtree)

```bash
# Publish a single page and all its content
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"publication.publish","arguments":{
      "path": "/sites/SITEKEY/home/sial-innovation",
      "languages": ["fr"],
      "includeSubTree": true
    }}
  }' | python3 -m json.tool
```

### Search for existing nodes

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.search","arguments":{
      "siteKey": "SITEKEY",
      "nodeType": "sialp:pageHero",
      "locale": "fr",
      "projectProperties": ["jcr:title", "backgroundImageUrl"],
      "limit": 50
    }}
  }' | python3 -m json.tool
```

### List children of a node

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.list","arguments":{
      "parentPath": "/sites/SITEKEY/home/sial-innovation/main",
      "locale": "fr"
    }}
  }' | python3 -m json.tool
```

---

## Step 0: Sitemap completeness check (run before any content creation)

Before creating any content, verify that every page in the reference site's navigation has a corresponding `jnt:page` in JCR. Discovering a missing page after content is created wastes time.

### 0a: Get JCR page list

```bash
source $(find . -name "migration.env" | head -1)

curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"page.list\",\"arguments\":{\"siteKey\":\"$JAHIA_SITE_KEY\",\"locale\":\"fr\",\"limit\":100}}}" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
content = d.get('result',{}).get('content',[{}])[0].get('text','{}')
pages = json.loads(content)
for p in pages.get('pages',[]):
    print(p.get('path',''))
" | sort > /tmp/jcr-pages.txt

echo "JCR pages found: $(wc -l < /tmp/jcr-pages.txt)"
cat /tmp/jcr-pages.txt
```

### 0b: Get reference site page list from content-data.json

```bash
python3 -c "
import json
data = json.load(open('workflow-output/content-data.json'))
pages = data.get('subPages', [])
for p in pages:
    slug = p.get('slug','')
    if slug:
        print(slug)
" | sort > /tmp/reference-slugs.txt

echo "Reference pages: $(wc -l < /tmp/reference-slugs.txt)"
cat /tmp/reference-slugs.txt
```

### 0c: Diff — find missing pages

```bash
python3 - << 'EOF'
import json

with open('/tmp/jcr-pages.txt') as f:
    jcr_paths = set(l.strip().split('/')[-1] for l in f if l.strip())

with open('/tmp/reference-slugs.txt') as f:
    ref_slugs = set(l.strip() for l in f if l.strip())

missing = ref_slugs - jcr_paths
extra = jcr_paths - ref_slugs - {'home', ''}

print(f"Missing from JCR ({len(missing)} pages):")
for s in sorted(missing):
    print(f"  MISSING: {s}")

print(f"\nExtra in JCR not in reference ({len(extra)}):")
for s in sorted(extra):
    print(f"  EXTRA: {s}")

if not missing:
    print("\nAll reference pages exist in JCR. Proceed with content creation.")
else:
    print(f"\nACTION REQUIRED: Create {len(missing)} missing pages before populating content.")
EOF
```

If any pages are missing, create them with `page.create` before proceeding to content creation. Never skip this check.

---

## Execution order: home page first, screenshot gate, then sub-pages

**Never defer content creation until after visual validation.** Components without JCR content look broken — collapsed carousels, missing icons, empty grids look identical to CSS failures. The correct workflow is:

1. **Create home page content first** (absolute area + all home page component instances)
2. **Publish everything** via `publication.publish` with `includeSubTree: true`
3. **Take a screenshot and present to user for VALIDATED gate**
4. Only after VALIDATED: create sub-page content

---

## Sub-page ISO migration: visual analysis per page (CRITICAL)

**The single most common mistake in sub-page migration is using generic components instead of page-specific ones.**

Each sub-page of the reference site typically uses a distinct visual layout pattern. Before populating ANY sub-page, you MUST:

### Step A: Screenshot each sub-page of the reference site

For every URL in the navigation (L1 landing pages AND all L2/L3 sub-pages), take a screenshot and identify the exact CSS class names used. Class names are non-negotiable — they are what makes the page look like the reference.

### Step B: Identify if new components are needed

Before creating content, check:
```bash
grep -r "className.*<css-class>" projects/<module>/src/components/
```

If NO component outputs the required class, build it first via `/jahia-dev-build-component`. **Never populate pages with a generic component because the correct one does not exist yet.**

### Step C: Discover the page structure before creating content

Always call `page.structure` on the target page before adding content to it:

```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"page.structure","arguments":{"path":"/sites/SITEKEY/home/sial-innovation"}}}' \
  | python3 -m json.tool
```

This reveals the exact area paths (e.g. `/sites/SITEKEY/home/sial-innovation/main`) to use as `parentPath` in `content.create`.

### Step D: Extract verbatim text content per page

Use browser MCP `get_page_text` on each reference URL. Extract:
- Banner: watermark text + h1 heading
- Each content block: watermarkWord, h2, body text, CTA label
- Info cards: icon class, title, body

### Step E: Populate in order

1. Build any missing components
2. Use `page.structure` to discover the area path
3. Use `content.create` (with `children` for containers) to add components
4. Use `publication.publish` with `includeSubTree: true` on the page

### Step D1: Mandatory field validation before publish

After creating each page's content nodes and before publishing, verify no mandatory field is empty. An empty mandatory field (e.g. hero with no heading) creates a broken published page.

```bash
# Check a page's content nodes for empty mandatory properties
PAGE_PATH="/sites/$JAHIA_SITE_KEY/home/my-page"

curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"content.list\",\"arguments\":{\"parentPath\":\"$PAGE_PATH/main\",\"locale\":\"fr\"}}}" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
content = d.get('result',{}).get('content',[{}])[0].get('text','{}')
nodes = json.loads(content).get('children',[])
for n in nodes:
    path = n.get('path','')
    props = n.get('properties',{})
    empty = [k for k,v in props.items() if v in (None, '', []) and not k.startswith('jcr:')]
    if empty:
        print(f'WARNING: {path} has empty fields: {empty}')
    else:
        print(f'OK: {path}')
"
```

Fix any WARNING before calling `publication.publish`. A node with an empty mandatory field publishes successfully but renders broken.

---

### Step D2: Populate the second language (MANDATORY)

Every site must ship EN and FR at minimum. After populating all content in the primary locale (`$JAHIA_SITE_KEY`'s default language), populate translations for every node using `content.translate`.

```bash
# Translate a content node to English after creating it in French
curl -s -X POST $JAHIA_URL/modules/mcp \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.translate","arguments":{
      "path": "/sites/SITEKEY/home/my-page/main/my-hero",
      "locale": "en",
      "properties": {
        "jcr:title": "English title here",
        "subtitle": "English subtitle"
      }
    }}
  }' | python3 -m json.tool
```

**Workflow:** create in primary locale -> translate to secondary locale(s) -> publish with all languages:

```bash
curl -s -X POST $JAHIA_URL/modules/mcp \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"publication.publish","arguments":{
      "path": "/sites/SITEKEY/home/my-page",
      "languages": ["fr", "en"],
      "includeSubTree": true
    }}
  }' | python3 -m json.tool
```

Non-i18n properties (images, dates, booleans) are shared across locales - only translate string/richtext fields marked `i18n` in the CND. Check with `content.type` if unsure which fields need translation.

---

### Step F: Per-page visual diff (MANDATORY)

After populating AND publishing each page, screenshot both the reference and Jahia render and compare before moving on:

```bash
SLUG="sial-innovation"
REFERENCE_URL="https://www.sialparis.com/fr-FR/temps-forts/sial-innovation"
JAHIA_URL="http://localhost:8080/cms/render/live/fr/sites/SITEKEY/home/temps-forts/sial-innovation.html"
mkdir -p /tmp/visual-diff/$SLUG

node -e "
const puppeteer = require('puppeteer');
(async () => {
  const b = await puppeteer.launch({ args: ['--no-sandbox'] });
  const ref = await b.newPage();
  await ref.setViewport({ width: 1440, height: 900 });
  await ref.goto('$REFERENCE_URL', { waitUntil: 'networkidle2', timeout: 30000 });
  await ref.screenshot({ path: '/tmp/visual-diff/$SLUG/reference.png', fullPage: true });

  const jahia = await b.newPage();
  await jahia.setViewport({ width: 1440, height: 900 });
  await jahia.goto('http://localhost:8080/cms/login', { waitUntil: 'networkidle2' });
  await jahia.type('#username', 'root');
  await jahia.type('#password', 'root');
  await Promise.all([jahia.waitForNavigation(), jahia.keyboard.press('Enter')]);
  await jahia.goto('$JAHIA_URL', { waitUntil: 'networkidle2' });
  await jahia.screenshot({ path: '/tmp/visual-diff/$SLUG/jahia.png', fullPage: true });
  await b.close();
})();
"
```

Per-page checklist:
```
[ ] Hero background image: present / blank
[ ] Hero heading text: correct / wrong
[ ] Section count: N reference vs N Jahia
[ ] Column layout: correct / stacked when should be side-by-side
[ ] Push cards count: N reference vs N Jahia
[ ] All images: present / N missing
[ ] CTA buttons: present and styled correctly
```

Save gap notes to `workflow-output/visual-diff/<slug>-gaps.md`. After all pages: run `/12-visual-diff`.

### Hero and section images (mandatory — never leave blank)

Never populate a page without its images. Images are the most visible ISO fidelity failure.

**Preferred: use `media.upload.url` directly:**
```bash
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"media.upload.url","arguments":{
      "siteKey": "SITEKEY",
      "sourceUrl": "https://www.sialparis.com/-/media/.../hero.jpg",
      "folder": "imported-images/heroes",
      "fileName": "sial-innovation-hero.jpg",
      "mimeType": "image/jpeg"
    }}
  }' | python3 -m json.tool
```

**Fallback: if `media.upload.url` fails** (CDN blocks, 403, redirect loop), use the image proxy:
```bash
curl -s "http://localhost:8080/modules/jahia-image-proxy/import-image\
?sourceUrl=https://www.sialparis.com/-/media/.../hero.jpg\
&destPath=/sites/SITEKEY/files/imported-images/heroes\
&filename=sial-innovation-hero.jpg\
&referer=https://www.sialparis.com"
```

Both return a JCR path. Use it as the `backgroundImageUrl` string property or as a WEAKREFERENCE value on image fields.

---

## Step G: Rich text internal link rewriting

After all content is populated, any rich text fields (type `richtext` in CND) that were copied from the reference site may contain absolute internal links pointing to the old domain. These become broken cross-domain links in production.

### Detect affected content nodes

```bash
source $(find . -name "migration.env" | head -1)

# Read reference domain from crawl output
REFERENCE_DOMAIN=$(python3 -c "
import json
try:
    data = json.load(open('workflow-output/content-data.json'))
    url = data.get('url', data.get('referenceUrl', ''))
    from urllib.parse import urlparse
    print(urlparse(url).netloc)
except:
    print('')
" 2>/dev/null)

if [ -z "$REFERENCE_DOMAIN" ]; then
  echo "Could not detect reference domain. Enter it manually (e.g. www.sialparis.com):"
  read REFERENCE_DOMAIN
fi

echo "Scanning for internal links pointing to: $REFERENCE_DOMAIN"

curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"content.search\",\"arguments\":{
    \"siteKey\": \"$JAHIA_SITE_KEY\",
    \"query\": \"$REFERENCE_DOMAIN\",
    \"workspace\": \"default\"
  }}}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
content = d.get('result',{}).get('content',[{}])[0].get('text','{}')
results = json.loads(content)
nodes = results.get('nodes', [])
print(f'Found {len(nodes)} nodes with references to old domain:')
for n in nodes:
    print(' ', n.get('path',''))
" 2>/dev/null || echo "content.search not available - use GraphQL fallback below"
```

GraphQL fallback if `content.search` MCP tool is unavailable:

```bash
curl -s -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -H "Origin: $JAHIA_URL" \
  -X POST "$JAHIA_URL/modules/graphql" \
  -d "{\"query\": \"{ jcr { nodesByQuery(query: \\\"SELECT * FROM [nt:base] WHERE CONTAINS(., '$REFERENCE_DOMAIN') AND ISDESCENDANTNODE('/sites/$JAHIA_SITE_KEY')\\\", queryLanguage: JCR_SQL2) { nodes { path properties { name value } } } } }\"}" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
nodes = d.get('data',{}).get('jcr',{}).get('nodesByQuery',{}).get('nodes',[])
print(f'{len(nodes)} nodes found with old domain references:')
for n in nodes:
    props = [p for p in n.get('properties',[]) if '$REFERENCE_DOMAIN' in (p.get('value') or '')]
    for p in props:
        print(f\"  {n['path']} -> {p['name']}\")
"
```

### Rewrite strategy

For each affected node, choose the appropriate fix:

**Option A - Remove domain (make relative)**
If the old URL maps to a page that exists in Jahia, strip the domain to make the link relative. Best for internal page links in body text.

```bash
# Example: rewrite https://www.sialparis.com/fr-FR/exposer -> /cms/render/live/fr/sites/SITEKEY/home/exposer.html
# Or better: change to a j:linkType weakreference pointing to the Jahia page node
```

**Option B - Replace with Jahia node reference**
For CTA links that were stored as plain strings: update the property to use `j:linkType=internal` + `j:linknode` pointing to the correct Jahia page node. Use MCP `content.update`.

**Option C - Replace with external link**
If the old URL points to a page NOT migrated to Jahia (flagged in `workflow-output/crawl-errors.txt`): keep as external link, set `j:linkType=external`, `j:url=https://archive.oldsite.com/...`.

### Bulk domain rewrite for richtext fields

For richtext properties containing multiple inline links, use a find-and-replace via MCP:

```bash
python3 - << 'EOF'
import subprocess, json, os

source_domain = os.environ.get('REFERENCE_DOMAIN', 'www.sialparis.com')
jahia_url = os.environ['JAHIA_URL']
user = os.environ['JAHIA_USER']
passwd = os.environ['JAHIA_PASS']
site_key = os.environ['JAHIA_SITE_KEY']

# Nodes found above - fill in from the search results
affected_nodes = [
    # { "path": "/sites/SITEKEY/home/my-page/main/article", "property": "body" },
]

for node in affected_nodes:
    # Get current value
    result = subprocess.run([
        'curl', '-s', '-X', 'POST', f'{jahia_url}/modules/mcp',
        '-u', f'{user}:{passwd}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "content.get", "arguments": {"path": node["path"]}}
        })
    ], capture_output=True, text=True)

    data = json.loads(result.stdout)
    content_text = data.get('result',{}).get('content',[{}])[0].get('text','{}')
    node_data = json.loads(content_text)

    props = node_data.get('properties', {})
    old_value = props.get(node["property"], '')
    if not old_value or source_domain not in old_value:
        continue

    # Strip domain from internal links
    new_value = old_value.replace(f'https://{source_domain}', '').replace(f'http://{source_domain}', '')

    # Update via MCP
    subprocess.run([
        'curl', '-s', '-X', 'POST', f'{jahia_url}/modules/mcp',
        '-u', f'{user}:{passwd}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "content.update", "arguments": {
                "path": node["path"],
                "properties": {node["property"]: new_value}
            }}
        })
    ], capture_output=True, text=True)

    print(f"Rewritten: {node['path']} -> {node['property']}")

print("Done. Re-publish affected pages after this step.")
EOF
```

After rewriting, publish the affected pages:

```bash
curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"publication.publish\",\"arguments\":{
    \"paths\": [\"/sites/$JAHIA_SITE_KEY\"],
    \"languages\": [\"fr\",\"en\"],
    \"includeSubTree\": true
  }}}"
```

**Never skip this step** if rich text content was imported from the reference site. A broken internal link in body text is invisible during development and only fails when a visitor clicks it.

---

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `parentPath not found` | Area path does not exist yet | Call `page.structure` first to discover the real area path |
| `nodeType not allowed here` | Wrong area or container type constraint | Check `page.structure` output for allowed types at that path |
| `locale required` | Missing `locale` in the call | Always pass `locale: "fr"` (or the site's language) |
| `media.upload.url` HTTP error | CDN blocks the fetch | Use the image proxy fallback with `&referer=` |
| Node created but not visible in live | Not published | Call `publication.publish` with `includeSubTree: true` |
| Property set but shows old value | i18n property set without correct locale | Ensure `locale` matches the site language |

---

## j:linkType links via MCP

**NEVER use `j:linkType: "external"` to link to an internal Jahia page.**

```bash
# Internal link
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.update","arguments":{
      "path": "/sites/SITEKEY/home/my-page/main/my-card",
      "locale": "fr",
      "addMixins": ["jmix:internalLink"],
      "properties": {
        "j:linkType": "internal",
        "j:linknode": "/sites/SITEKEY/home/target-page"
      }
    }}
  }' | python3 -m json.tool

# External link
curl -s -X POST http://localhost:8080/modules/mcp \
  -u root:root -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"content.update","arguments":{
      "path": "/sites/SITEKEY/home/my-page/main/my-card",
      "locale": "fr",
      "addMixins": ["jmix:externalLink"],
      "properties": {
        "j:linkType": "external",
        "j:url": "https://example.com"
      }
    }}
  }' | python3 -m json.tool
```

---

## References

- MCP server: `http://localhost:8080/modules/mcp` (GET = tool list, POST JSON-RPC = execute)
- Jahia credentials: root / root (local dev)
- Image proxy (fallback): `http://localhost:8080/modules/jahia-image-proxy/import-image`
- JCR browser (inspect nodes): `http://localhost:8080/modules/tools/jcrBrowser.jsp`
