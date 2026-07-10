#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo "=== STEP 10 — Verification ==="

# Check home page renders (live)
echo ""
echo "1. Checking home page accessibility..."
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -u "$JAHIA_USER" \
  "http://localhost:8080/sites/sial-paris/home.html")
echo "   HTTP status: $HTTP"

# Count published nodes
echo ""
echo "2. Counting published content..."
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodesByQuery(query: \"SELECT * FROM [jnt:content] WHERE ISDESCENDANTNODE(\\\"/sites/sial-paris/home\\\")\", queryLanguage: SQL2) { nodes { path } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
try:
  d = json.load(sys.stdin)
  nodes = d.get('data',{}).get('jcr',{}).get('nodesByQuery',{}).get('nodes',[])
  print(f"   Published content nodes: {len(nodes)}")
  print("")
  print("   Sample nodes:")
  for n in nodes[:15]:
    print(f"     {n['path']}")
  if len(nodes) > 15:
    print(f"     ... and {len(nodes) - 15} more")
except Exception as e:
  print(f"   Error: {e}")
PYTHON

# Check sub-pages
echo ""
echo "3. Checking sub-pages..."
for slug in le-salon les-exposants temps-forts tendances infos-pratiques medias; do
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" -u "$JAHIA_USER" \
    "http://localhost:8080/sites/sial-paris/home/${slug}.html")
  echo "   /$slug: HTTP $HTTP"
done

# Check news articles
echo ""
echo "4. Checking news articles..."
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodesByQuery(query: \"SELECT * FROM [sialp:newsArticle] WHERE ISDESCENDANTNODE(\\\"/sites/sial-paris/contents/news\\\")\", queryLanguage: SQL2) { nodes { name } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
try:
  d = json.load(sys.stdin)
  nodes = d.get('data',{}).get('jcr',{}).get('nodesByQuery',{}).get('nodes',[])
  print(f"   News articles published: {len(nodes)}")
  for n in nodes:
    print(f"     - {n['name']}")
except Exception as e:
  print(f"   Error: {e}")
PYTHON

# List all home page components
echo ""
echo "5. Home page component inventory..."
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home\") { descendants { nodes { name primaryNodeType { name } } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
try:
  d = json.load(sys.stdin)
  nodes = d.get('data',{}).get('jcr',{}).get('nodeByPath',{}).get('descendants',{}).get('nodes',[])
  
  # Count by type
  by_type = {}
  for n in nodes:
    t = n['primaryNodeType']['name']
    by_type[t] = by_type.get(t, 0) + 1
  
  print("   Components by type:")
  for t in sorted(by_type.keys()):
    print(f"     {t}: {by_type[t]}")
    
except Exception as e:
  print(f"   Error: {e}")
PYTHON

echo ""
echo "=== VERIFICATION COMPLETE ==="
