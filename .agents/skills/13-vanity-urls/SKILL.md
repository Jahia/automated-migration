---
name: 13-vanity-urls
description: Map old site URLs to Jahia pages via vanity URLs. Ensures inbound links, bookmarks, and search engine index entries continue to work after go-live. Run after content is populated (skill 09) and before sign-off.
type: workflow
phase: 13
status: active
depends_on:
  - 9-create-content
allowed-tools: Bash, Read, Write, WebFetch
---

# Skill: Vanity URLs

Maps every public URL from the reference site to its corresponding Jahia page via Jahia's built-in vanity URL system. Without this, all inbound links, bookmarks, and Google index entries break on go-live.

---

## Agent identity
- **Agent name:** Routex
- **Reference style:** Router / redirector
- **Signature line (en):** *"Every old URL finds its new home."*
- **Personality note:** Systematic mapper. Builds the full URL inventory, matches every path to a Jahia page, creates vanity URLs for all matches, flags unmatched paths. Never skips a URL.
- **Usage rule:** Brief invocation only in orchestrator narration. Never appears in deliverables.

---

## Load migration environment

```bash
ENV_FILE=$(find . -name "migration.env" | head -1)
if [ -z "$ENV_FILE" ]; then
  echo "ERROR: migration.env not found. Run /0-migration-start first."
  exit 1
fi
source "$ENV_FILE"
echo "Jahia: $JAHIA_URL | Site: $JAHIA_SITE_KEY | MCP: $MCP_AVAILABLE"
```

---

## Step 1: Build the old URL inventory

Read the crawled URL list from skill 01 and extract all page paths:

```bash
# Primary source: wget crawl log
find /tmp/website-download -name "*.html" 2>/dev/null \
  | sed "s|/tmp/website-download/||" \
  | sed "s|/index.html||" \
  | sort -u > /tmp/old-urls.txt

# Supplement with content-data.json sub-pages
python3 - << 'EOF'
import json, os

try:
    data = json.load(open('workflow-output/content-data.json'))
    pages = data.get('subPages', [])
    with open('/tmp/old-urls.txt', 'a') as f:
        for p in pages:
            url = p.get('url', '')
            if url:
                from urllib.parse import urlparse
                path = urlparse(url).path.rstrip('/')
                f.write(path + '\n')
    print(f"Added {len(pages)} URLs from content-data.json")
except Exception as e:
    print(f"content-data.json not found or unreadable: {e}")
EOF

# Deduplicate
sort -u /tmp/old-urls.txt -o /tmp/old-urls.txt
wc -l /tmp/old-urls.txt
echo "=== Old site URLs ==="
cat /tmp/old-urls.txt
```

---

## Step 2: Build the Jahia page inventory

Get all live pages from Jahia with their paths:

```bash
curl -s -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -H "Origin: $JAHIA_URL" \
  -X POST "$JAHIA_URL/modules/graphql" \
  -d "{\"query\": \"{ jcr { nodeByPath(path: \\\"/sites/$JAHIA_SITE_KEY/home\\\") { descendants(typesFilter: {types: [\\\"jnt:page\\\"]}) { nodes { path name urlKey: property(name: \\\"j:nodename\\\") { value } } } } } }\"}" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
nodes = d.get('data',{}).get('jcr',{}).get('nodeByPath',{}).get('descendants',{}).get('nodes',[])
for n in nodes:
    # Convert JCR path to live render URL path segment
    jcr_path = n['path']
    # /sites/SITEKEY/home/section/page -> /section/page
    slug = jcr_path.replace(f'/sites/{\"$JAHIA_SITE_KEY\"}/home', '')
    print(jcr_path + '\t' + slug)
" > /tmp/jahia-pages.txt

echo "Jahia pages found: $(wc -l < /tmp/jahia-pages.txt)"
cat /tmp/jahia-pages.txt
```

---

## Step 3: Generate URL mapping

Match each old URL to a Jahia page path. The matching logic normalizes both sides:
- Strip language prefix (`/fr-FR/`, `/en/`, `/fr/`)
- Strip trailing slashes
- Lowercase both sides
- Try exact match, then slug-only match

```bash
python3 - << 'EOF'
import re, json, os

with open('/tmp/old-urls.txt') as f:
    old_urls = [l.strip() for l in f if l.strip()]

with open('/tmp/jahia-pages.txt') as f:
    jahia_entries = [l.strip().split('\t') for l in f if l.strip() and '\t' in l]

# Build jahia lookup: normalized_slug -> jcr_path
jahia_map = {}
for jcr_path, slug in jahia_entries:
    normalized = slug.lower().strip('/')
    jahia_map[normalized] = jcr_path

def normalize(url):
    # Remove language prefix: /fr-FR/x -> x, /fr/x -> x, /en/x -> x
    url = re.sub(r'^/[a-z]{2}(-[A-Z]{2})?/', '/', url)
    return url.lower().strip('/')

matched = []
unmatched = []

for old_url in old_urls:
    norm = normalize(old_url)
    if norm in jahia_map:
        matched.append({
            'oldUrl': old_url,
            'jahiaPath': jahia_map[norm],
            'vanityUrl': old_url  # the vanity URL to register on the Jahia page
        })
    else:
        # Try slug-only match (last path segment)
        slug = norm.split('/')[-1]
        candidates = [v for k, v in jahia_map.items() if k.endswith(slug)]
        if len(candidates) == 1:
            matched.append({
                'oldUrl': old_url,
                'jahiaPath': candidates[0],
                'vanityUrl': old_url,
                'matchType': 'slug-only'
            })
        else:
            unmatched.append(old_url)

os.makedirs('workflow-output', exist_ok=True)
with open('workflow-output/url-mapping.json', 'w') as f:
    json.dump({'matched': matched, 'unmatched': unmatched}, f, indent=2)

print(f"Matched:   {len(matched)}")
print(f"Unmatched: {len(unmatched)}")
if unmatched:
    print("\nUnmatched URLs (no Jahia page found):")
    for u in unmatched:
        print(f"  {u}")
EOF
```

### Review slug-only matches with the user

Before creating vanity URLs, show all `matchType: slug-only` matches for confirmation:

```
The following URL matches were made by slug only (last path segment).
Please confirm each is correct:

  /fr-FR/temps-forts/sial-innovation  ->  /sites/sitekey/home/temps-forts/sial-innovation  (OK)
  /fr-FR/innovation                    ->  /sites/sitekey/home/temps-forts/innovation        (CHECK)

Type CONFIRM to proceed, or correct any wrong mappings in workflow-output/url-mapping.json first.
```

---

## Step 4: Create vanity URLs in Jahia

Vanity URLs in Jahia are stored as `jnt:vanityUrl` child nodes under a `jnt:vanityUrls` container on each page.

**Check if MCP has a vanity URL tool first:**

```bash
curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
tools = [t['name'] for t in d.get('result',{}).get('tools',[]) if 'vanity' in t['name'].lower() or 'url' in t['name'].lower()]
print('URL-related MCP tools:', tools if tools else 'none found')
"
```

**If MCP has a vanity URL tool:** use it. Otherwise use GraphQL:

```bash
python3 - << 'EOF'
import json, subprocess, os

mapping = json.load(open('workflow-output/url-mapping.json'))
matched = mapping['matched']

jahia_url = os.environ['JAHIA_URL']
user = os.environ['JAHIA_USER']
passwd = os.environ['JAHIA_PASS']
site_key = os.environ['JAHIA_SITE_KEY']

# Detect site default language from content-data.json
try:
    data = json.load(open('workflow-output/content-data.json'))
    lang = data.get('defaultLocale', 'fr')[:2]
except:
    lang = 'fr'

success = 0
failed = []

for entry in matched:
    jcr_path = entry['jahiaPath']
    vanity = entry['vanityUrl']

    # Normalize vanity: strip language prefix, ensure leading slash
    import re
    vanity_clean = re.sub(r'^/[a-z]{2}(-[A-Z]{2})?', '', vanity)
    if not vanity_clean.startswith('/'):
        vanity_clean = '/' + vanity_clean

    mutation = """
    mutation {
      jcr {
        mutateNode(pathOrId: "%s") {
          addChild(name: "vanityUrlMapping", primaryNodeType: "jnt:vanityUrls") {
            addChild(name: "%s", primaryNodeType: "jnt:vanityUrl") {
              mutateProperty(name: "j:url") { setValue(value: "%s") }
              mutateProperty(name: "j:active") { setValue(value: "true") }
              mutateProperty(name: "j:default") { setValue(value: "false") }
              mutateProperty(name: "j:language") { setValue(value: "%s") }
            }
          }
        }
      }
    }
    """ % (jcr_path, vanity_clean.replace('/', '_').strip('_'), vanity_clean, lang)

    result = subprocess.run([
        'curl', '-s', '-u', f'{user}:{passwd}',
        '-H', 'Content-Type: application/json',
        '-H', f'Origin: {jahia_url}',
        '-X', 'POST', f'{jahia_url}/modules/graphql',
        '-d', json.dumps({'query': mutation})
    ], capture_output=True, text=True)

    resp = json.loads(result.stdout)
    if resp.get('errors'):
        err = resp['errors'][0].get('message', '')
        # Node may already exist — not a failure
        if 'already exists' in err or 'ItemExistsException' in err:
            print(f"SKIP (already exists): {vanity_clean}")
            success += 1
        else:
            print(f"FAILED: {vanity_clean} - {err}")
            failed.append({'vanity': vanity_clean, 'path': jcr_path, 'error': err})
    else:
        print(f"OK: {vanity_clean} -> {jcr_path}")
        success += 1

print(f"\nCreated: {success} / {len(matched)}")
if failed:
    print(f"Failed:  {len(failed)}")
    with open('workflow-output/vanity-errors.txt', 'w') as f:
        for e in failed:
            f.write(f"{e['vanity']} -> {e['path']}: {e['error']}\n")
    print("Errors written to workflow-output/vanity-errors.txt")
EOF
```

---

## Step 5: Publish vanity URL nodes

Vanity URLs must be published to take effect in the live workspace:

```bash
curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"publication.publish\",\"arguments\":{
    \"paths\": [\"/sites/$JAHIA_SITE_KEY\"],
    \"languages\": [\"fr\",\"en\"],
    \"includeSubTree\": true
  }}}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('result',{}).get('content',[{}])[0].get('text','done'))
"
```

---

## Step 6: Verify vanity URLs resolve

Test a sample of vanity URLs by hitting them directly:

```bash
python3 - << 'EOF'
import json, subprocess, os, random

mapping = json.load(open('workflow-output/url-mapping.json'))
matched = mapping['matched']

jahia_url = os.environ['JAHIA_URL']
user = os.environ['JAHIA_USER']
passwd = os.environ['JAHIA_PASS']

# Test up to 10 random vanity URLs
sample = random.sample(matched, min(10, len(matched)))

import re
for entry in sample:
    vanity = re.sub(r'^/[a-z]{2}(-[A-Z]{2})?', '', entry['vanityUrl'])
    test_url = f"{jahia_url}{vanity}"
    result = subprocess.run([
        'curl', '-s', '-o', '/dev/null', '-w', '%{http_code} %{redirect_url}',
        '-u', f'{user}:{passwd}',
        '-L', '--max-redirs', '3',
        test_url
    ], capture_output=True, text=True)
    status = result.stdout.strip()
    print(f"{'OK' if status.startswith('200') else 'FAIL'}: {vanity} -> {status}")
EOF
```

Expected: HTTP 200 (Jahia follows the vanity URL and renders the page directly, not a 301).

---

## Step 7: Generate redirect map for CDN / web server

For the go-live cutover, the client's CDN or web server also needs a redirect map to handle requests that hit the old domain before DNS is switched. Write an nginx-compatible map:

```bash
python3 - << 'EOF'
import json, re, os

mapping = json.load(open('workflow-output/url-mapping.json'))
site_key = os.environ['JAHIA_SITE_KEY']
jahia_url = os.environ.get('PRODUCTION_URL', os.environ['JAHIA_URL'])

lines = ['# Nginx redirect map — generated by migration skill 13', '# Add to nginx.conf: map $request_uri $redirect_uri { ... }', '']

for entry in mapping['matched']:
    old = entry['oldUrl']
    vanity = re.sub(r'^/[a-z]{2}(-[A-Z]{2})?', '', old)
    lines.append(f'~^{re.escape(old)}$   {vanity};')

for old in mapping['unmatched']:
    lines.append(f'# UNMATCHED: {old}')

with open('workflow-output/nginx-redirects.conf', 'w') as f:
    f.write('\n'.join(lines))

print(f"Written {len(mapping['matched'])} redirects to workflow-output/nginx-redirects.conf")
print(f"Unmatched (manual review needed): {len(mapping['unmatched'])}")
EOF
```

Present `workflow-output/url-mapping.json` and `workflow-output/nginx-redirects.conf` to the client as part of the go-live package.

---

## Validation checklist

- [ ] Old URL inventory built from wget crawl + content-data.json
- [ ] Jahia page inventory fetched
- [ ] URL mapping generated — matched and unmatched counts reviewed with user
- [ ] Slug-only matches confirmed by user
- [ ] Vanity URL nodes created in Jahia for all matched URLs
- [ ] Vanity URLs published to live workspace
- [ ] Sample verification: 10 random vanity URLs return HTTP 200
- [ ] `workflow-output/nginx-redirects.conf` written for CDN cutover
- [ ] Unmatched URLs flagged for manual handling or 410 Gone response
