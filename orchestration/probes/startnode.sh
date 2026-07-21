#!/usr/bin/env bash
# startnode.sh — UNGAMEABLE gate: every mainResource lsp:jcrQuery.startNode MUST
# resolve to a jnt:contentFolder (never a jnt:page / /home, never empty).
#
# This catches the core mainResource mis-wire: the listing query pointing at the
# home page instead of the contentFolder that holds the articles. Measures the
# real JCR state via MCP (not a proxy).
#
# Usage: bash orchestration/probes/startnode.sh <project> <site> [locale]
set -euo pipefail
PROJECT="${1:?project}"; SITE="${2:?site}"; LOCALE="${3:-fr}"
cd "$(dirname "$0")/../.." 2>/dev/null || true

python3 - "$PROJECT" "$SITE" "$LOCALE" <<'PY'
import json, sys
sys.path.insert(0, "orchestration/lib")
from mcp_client import MCP

project, site, locale = sys.argv[1], sys.argv[2], sys.argv[3]
m = MCP(project)

# mainResource types this source declares (from the manifest)
manifest = json.load(open(f"projects/{project}/workflow-output/component-manifest.json"))
mr_types = {c.get("nodeType") for c in manifest.get("components", []) if c.get("needsMainResource")}

# the listing type is the manifest's jcrQuery archetype (namespace-agnostic;
# the lsp: hardcode made this gate a no-op on every other project)
q_nt = next((c.get("nodeType") for c in manifest.get("components", [])
             if c.get("archetype") == "jcrQuery"), None) or \
    next((c.get("nodeType") for c in manifest.get("components", [])
          if c.get("nodeType", "").endswith(":jcrQuery")), "lsp:jcrQuery")

# NB: content.search silently returns empty for limit > 100 — keep it <= 100.
r = m.call("content.search", {"siteKey": site, "nodeType": q_nt,
                              "locale": locale, "limit": 100})
queries = r.get("results", r.get("nodes", [])) if isinstance(r, dict) else []

fails, checked = [], 0
for q in queries:
    qpath = q.get("path")
    d = m.get(qpath)
    props = d.get("properties", {}) or {}
    qtype = props.get("type")
    if qtype not in mr_types:
        continue  # only gate listings over mainResource types
    checked += 1
    sn = props.get("startNode")
    if not sn:
        fails.append(f"{qpath}: startNode EMPTY (type={qtype}) -> listing resolves nothing")
        continue
    try:
        tgt = m.call("content.get", {"uuid": sn, "locale": locale})
    except Exception as e:
        fails.append(f"{qpath}: startNode {sn} does not resolve ({str(e)[:60]})")
        continue
    tprops = tgt.get("properties", {}) or {}
    tprimary = tprops.get("jcr:primaryType")
    tpath = tgt.get("path")
    if tprimary != "jnt:contentFolder":
        fails.append(f"{qpath}: startNode -> {tpath} ({tprimary}) — MUST be jnt:contentFolder")

print(f"startnode.sh: checked {checked} mainResource listing quer{'y' if checked==1 else 'ies'}")
if fails:
    print("FAIL:")
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
if checked == 0:
    print("WARN: no mainResource jcrQuery nodes found (nothing to gate)")
print("PASS: all mainResource listings point at a jnt:contentFolder")
PY
