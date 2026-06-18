---
name: 0-migration-start
description: Entry point for every migration. Asks 3 mandatory questions (Jahia server, credentials, Docker container), verifies connectivity, and writes migration.env to the project. Run before any other skill.
type: workflow
phase: 0
status: active
invokes_workflow: true
depends_on: []
allowed-tools: Bash, Read, Write, WebFetch
---

# Skill: Migration Start

**This is the first skill that runs on every migration, without exception.**

It collects the 3 pieces of information every other skill needs, verifies they work, and writes them to `migration.env` in the project folder so no subsequent skill ever has to guess.

---

## Step 1: Ask the 3 mandatory questions

Stop and ask the user before doing anything else:

```
Before we start, I need 3 pieces of information:

1. Jahia server URL
   Where is Jahia running? (e.g. http://localhost:8080, https://jahia.mycompany.com)

2. Jahia credentials
   Root login and password for this instance?

3. Docker container name (if running locally)
   What is the Docker container name for Jahia?
   Run: docker ps --format '{{.Names}}' to find it.
   Leave blank if Jahia is not running in Docker (remote server, bare metal, etc.)
```

Wait for the user to answer all 3 before proceeding.

---

## Step 2: Verify connectivity

### 2a: Jahia health check — wait for full boot

```bash
JAHIA_URL="<answer from question 1>"
JAHIA_USER="<login from question 2>"
JAHIA_PASS="<password from question 2>"

echo "Waiting for Jahia to be fully booted..."
for i in $(seq 1 24); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -u "$JAHIA_USER:$JAHIA_PASS" \
    "$JAHIA_URL/modules/graphql" 2>/dev/null)
  if [ "$STATUS" = "200" ] || [ "$STATUS" = "405" ]; then
    echo "Jahia ready (HTTP $STATUS)"
    break
  fi
  echo "  Attempt $i/24: HTTP $STATUS — waiting 10s..."
  sleep 10
done

if [ "$STATUS" != "200" ] && [ "$STATUS" != "405" ]; then
  echo "ERROR: Jahia not reachable after 4 minutes (last status: $STATUS)"
  echo "Check: is Jahia running? Is the URL correct? Are credentials correct?"
  exit 1
fi
```

If running in Docker, also verify Karaf OSGi is fully started (not just the container):

```bash
CONTAINER="<answer from question 3>"
if [ -n "$CONTAINER" ]; then
  echo "Verifying Karaf is started inside container $CONTAINER..."
  docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$" || {
    echo "ERROR: container $CONTAINER not found in docker ps"
    echo "Run: docker ps --format '{{.Names}}' to find the correct name"
    exit 1
  }
  # Check Karaf is accepting HTTP (not just container running)
  KARAF_STATUS=$(docker exec "$CONTAINER" \
    curl -s -o /dev/null -w "%{http_code}" \
    -u "$JAHIA_USER:$JAHIA_PASS" \
    "http://localhost:8080/modules/graphql" 2>/dev/null)
  echo "Karaf internal HTTP: $KARAF_STATUS"
  if [ "$KARAF_STATUS" != "200" ] && [ "$KARAF_STATUS" != "405" ]; then
    echo "WARNING: Container is running but Karaf is not yet ready internally."
    echo "Wait another 60s and try again, or check: docker logs $CONTAINER | tail -50"
  fi
fi
```

### 2b: MCP availability check

```bash
curl -s "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print('MCP OK -', d.get('version','?'), '-', len(d.get('tools',[])), 'tools')
except:
    print('MCP NOT AVAILABLE - will fall back to GraphQL')
"
```

Record whether MCP is available. If available, all content operations in skills 09+ use MCP. If not, fall back to GraphQL (note this in `migration.env`).

### 2c: Docker container check (if provided)

```bash
CONTAINER="<answer from question 3>"

if [ -n "$CONTAINER" ]; then
  docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$" \
    && echo "Container $CONTAINER is running" \
    || echo "WARNING: container $CONTAINER not found in docker ps"
fi
```

If not found, ask the user to recheck the container name. The container name is needed for deploying OSGi bundles:
```bash
docker cp target/*.jar $CONTAINER:/var/jahia/karaf/deploy/
```

### 2d: Site list (what sites exist)

```bash
curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"site.list","arguments":{}}}' \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
content = d.get('result', {}).get('content', [{}])[0].get('text', '{}')
sites = json.loads(content)
for s in sites.get('sites', []):
    print(s.get('siteKey'), '-', s.get('title',''))
"
```

Show the list to the user and ask:

```
Which site key are we migrating to?
  - Enter an existing site key from the list above, OR
  - Enter a NEW site key to create a fresh site (e.g. my-client-2026)
```

### 2e: Create site if it does not exist

If the user provides a site key that is NOT in the list above, create it using MCP:

```bash
# First, discover available template sets
curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"site.template_sets","arguments":{}}}' \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
content = d.get('result',{}).get('content',[{}])[0].get('text','{}')
sets = json.loads(content)
for s in sets.get('templateSets', []):
    print(s.get('id',''), '-', s.get('title',''))
"
```

Show the available template sets to the user. For a JS module migration, the template set will be the module being built (it will be deployed in step 2). Ask:

```
Template set to use? (Enter the module ID, e.g. sial-paris)
Site display title? (e.g. SIAL Paris)
Default language? (e.g. fr)
Additional languages? (e.g. en — comma-separated, or leave blank)
```

Then create the site:

```bash
NEW_SITE_KEY="<user answer>"
TEMPLATE_SET="<user answer>"
SITE_TITLE="<user answer>"
SITE_LOCALE="<user answer, e.g. fr>"

curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d "{
    \"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",
    \"params\":{\"name\":\"site.create\",\"arguments\":{
      \"siteKey\": \"$NEW_SITE_KEY\",
      \"templateSet\": \"$TEMPLATE_SET\",
      \"title\": \"$SITE_TITLE\",
      \"locale\": \"$SITE_LOCALE\",
      \"serverName\": \"localhost\"
    }}
  }" | python3 -m json.tool
```

Verify creation by calling `site.get`:

```bash
curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"site.get\",\"arguments\":{\"siteKey\":\"$NEW_SITE_KEY\"}}}" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
content = d.get('result',{}).get('content',[{}])[0].get('text','{}')
site = json.loads(content)
print('Site created:', site.get('siteKey'), '-', site.get('title',''))
print('Homepage:', site.get('homePath',''))
print('Languages:', site.get('languages',''))
"
```

If site creation fails with "template set not found": the JS module has not been deployed yet. Note this - the module must be deployed (step 2) before the site can be created with it as the template set. In this case:
1. Create the site now with a placeholder template set (e.g. `digitall` or the first available one)
2. After step 2 deploys the module, re-assign the template set via jContent > Site Settings

Record the chosen site key in `migration.env` as `JAHIA_SITE_KEY`.

---

## Step 3: Write migration.env

Find the project folder:
```bash
find . -name "definitions.cnd" -path "*/settings/*" | head -1
# grandparent of that file is the module root
```

Write `<project-root>/migration.env`:

```bash
cat > <project-root>/migration.env << EOF
# Generated by skill 00-migration-start
# DO NOT commit this file — it contains credentials

JAHIA_URL=<answer 1>
JAHIA_USER=<answer 2 login>
JAHIA_PASS=<answer 2 password>
JAHIA_CONTAINER=<answer 3, or empty if not Docker>
JAHIA_SITE_KEY=<answer from site list>
MCP_AVAILABLE=<true or false>
EOF
```

Add `migration.env` to `.gitignore` if not already there:
```bash
grep -q "migration.env" <project-root>/.gitignore 2>/dev/null \
  || echo "migration.env" >> <project-root>/.gitignore
```

---

## Step 4: Report and proceed

Print a confirmation:

```
MIGRATION ENVIRONMENT CONFIGURED

Jahia URL:   <url>
Credentials: <user> / ****
Docker:      <container or "not Docker">
Site key:    <siteKey>
MCP:         <available / not available>

migration.env written to <project-root>/migration.env
All subsequent skills will read from this file.

Ready to start. Proceed with /1-analyze <reference-site-url>
```

---

## How subsequent skills use migration.env

Every skill that calls Jahia reads from `migration.env` at the start of its execution:

```bash
# Load environment at the top of every skill session
source <project-root>/migration.env

# Then use variables directly — no hardcoding
curl -s -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  "$JAHIA_URL/modules/graphql" ...

# MCP calls
curl -s -X POST "$JAHIA_URL/modules/mcp" \
  -u "$JAHIA_USER:$JAHIA_PASS" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"site.list","arguments":{}}}' ...

# OSGi deploy
docker cp target/*.jar "$JAHIA_CONTAINER:/var/jahia/karaf/deploy/"
```

**If `migration.env` does not exist when a skill starts:** the skill MUST stop and ask the user to run `/0-migration-start` first. Never guess credentials or URLs.
