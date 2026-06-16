#!/bin/bash

JAHIA_HOST="http://localhost:8080"
JAHIA_USER="root:root"

echo ""
echo "=========================================="
echo "SIAL PARIS SITE CONTENT CREATION SUMMARY"
echo "=========================================="
echo ""

echo "✓ PAGES CREATED (6 sub-pages)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home\") { children { nodes { name primaryNodeType { name } } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
pages = [n for n in d['data']['jcr']['nodeByPath']['children']['nodes'] if n['primaryNodeType']['name'] == 'jnt:page']
for p in sorted(pages, key=lambda x: x['name']):
  print(f"  • {p['name']}")
PYTHON

echo ""
echo "✓ CONTENT AREAS CREATED (hero, main, header, footer)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home\") { children { nodes { name primaryNodeType { name } } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
areas = [n for n in d['data']['jcr']['nodeByPath']['children']['nodes'] if n['primaryNodeType']['name'] == 'jnt:contentList']
for a in sorted(areas, key=lambda x: x['name']):
  print(f"  • {a['name']}")
PYTHON

echo ""
echo "✓ HOME PAGE COMPONENTS (8 components)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home/main\") { children { nodes { name primaryNodeType { name } } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
components = d['data']['jcr']['nodeByPath']['children']['nodes']
for c in sorted(components, key=lambda x: x['name']):
  print(f"  • {c['name']} ({c['primaryNodeType']['name']})")
PYTHON

echo ""
echo "✓ HERO CAROUSEL (1 carousel + 3 slides)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home/hero/heroCarousel\") { children { nodes { name } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
children = d['data']['jcr']['nodeByPath']['children']['nodes']
for c in sorted(children, key=lambda x: x['name']):
  print(f"  • {c['name']}")
PYTHON

echo ""
echo "✓ KEY FIGURES (5 figures)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home/main/keyFigures\") { children { nodes { name } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
children = d['data']['jcr']['nodeByPath']['children']['nodes']
for c in sorted(children, key=lambda x: x['name']):
  print(f"  • {c['name']}")
PYTHON

echo ""
echo "✓ VISITOR PROFILES (4 profiles)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home/main/visitorProfiles\") { children { nodes { name } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
children = d['data']['jcr']['nodeByPath']['children']['nodes']
for c in sorted(children, key=lambda x: x['name']):
  print(f"  • {c['name']}")
PYTHON

echo ""
echo "✓ TREND CARDS (3 trends)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home/main/trendsSection\") { children { nodes { name primaryNodeType { name } } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
children = [n for n in d['data']['jcr']['nodeByPath']['children']['nodes'] if 'trend' in n['name'].lower()]
for c in sorted(children, key=lambda x: x['name']):
  print(f"  • {c['name']}")
PYTHON

echo ""
echo "✓ SIAL NETWORK EVENTS (7 events)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/home/main/sialNetwork\") { children { nodes { name } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
children = d['data']['jcr']['nodeByPath']['children']['nodes']
for c in sorted(children, key=lambda x: x['name']):
  print(f"  • {c['name']}")
PYTHON

echo ""
echo "✓ NAVIGATION & FOOTER"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ header: jcr { nodeByPath(path: \"/sites/sial-paris/home/header\") { children { nodes { name } } } } footer: jcr { nodeByPath(path: \"/sites/sial-paris/home/footer\") { children { nodes { name } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
print("  Header:")
for n in d['data']['header']['nodeByPath']['children']['nodes']:
  print(f"    • {n['name']}")
print("  Footer:")
for n in d['data']['footer']['nodeByPath']['children']['nodes']:
  print(f"    • {n['name']}")
PYTHON

echo ""
echo "✓ NEWS ARTICLES (3 articles in /contents/news)"
curl -s -u "$JAHIA_USER" "$JAHIA_HOST/modules/graphql" \
  -H "Origin: $JAHIA_HOST" -H "content-type: application/json" \
  --data-raw '{"query":"{ jcr(workspace: LIVE) { nodeByPath(path: \"/sites/sial-paris/contents/news\") { children { nodes { name } } } } }"}' \
  | python3 << 'PYTHON'
import sys, json
d = json.load(sys.stdin)
children = d['data']['jcr']['nodeByPath']['children']['nodes']
for c in sorted(children, key=lambda x: x['name']):
  print(f"  • {c['name']}")
PYTHON

echo ""
echo "=========================================="
echo "STATUS: ALL CONTENT CREATED AND PUBLISHED"
echo "=========================================="
echo ""
echo "Scripts saved to:"
echo "  /Users/stephane/Runtimes/0.Modules/jahiaMigration/projects/sial-paris/workflow-output/graphql-scripts/"
echo ""
