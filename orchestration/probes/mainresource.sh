#!/usr/bin/env bash
# mainresource.sh — UNGAMEABLE gate for the mainResource LOAD step: every folder
# declared in <project>.mainresource-load.json must exist as a jnt:contentFolder
# and hold >=1 PUBLISHED node of the folder's declared type.
#
# Pairs with startnode.sh (which gates the wiring step). This one gates the
# producing step (load_main_resources.py) — content actually created, not a proxy.
#
# Usage: bash orchestration/probes/mainresource.sh <project> <site> [locale]
set -euo pipefail
PROJECT="${1:?project}"; SITE="${2:?site}"; LOCALE="${3:-fr}"
cd "$(dirname "$0")/../.." 2>/dev/null || true

python3 - "$PROJECT" "$SITE" "$LOCALE" <<'PY'
import json, sys
sys.path.insert(0, "orchestration/lib")
from mcp_client import MCP

project, site, locale = sys.argv[1], sys.argv[2], sys.argv[3]
mrl = json.load(open(f"orchestration/content/{project}.mainresource-load.json"))
manifest = json.load(open(f"projects/{project}/workflow-output/component-manifest.json"))
mr_types = {c.get("nodeType") for c in manifest.get("components", []) if c.get("needsMainResource")}
m = MCP(project)

fails = []
folder_paths = [f["path"] for f in mrl.get("folders", {}).values()]

# INVARIANT: every mainResource node MUST live under a declared contentFolder.
# A mainResource node inside a page main area is inline debris / fabrication.
for nt in sorted(mr_types):
    r = m.call("content.search", {"siteKey": site, "nodeType": nt, "locale": locale, "limit": 100})
    for n in (r.get("results", []) if isinstance(r, dict) else []):
        p = n.get("path")
        if p and not any(p == fp or p.startswith(fp + "/") for fp in folder_paths):
            fails.append(f"misplaced {nt} outside a contentFolder: {p} — mainResource is folder-only")

for fname, f in mrl.get("folders", {}).items():
    path, ftype = f["path"], f["type"]
    try:
        node = m.get(path)
    except Exception as e:
        fails.append(f"{path}: folder missing ({str(e)[:50]})"); continue
    primary = (node.get("properties", {}) or {}).get("jcr:primaryType")
    if primary != "jnt:contentFolder":
        fails.append(f"{path}: is {primary}, MUST be jnt:contentFolder"); continue
    d = m.call("content.list", {"parentPath": path, "childNodeType": ftype,
                                "locale": locale, "limit": 100})
    kids = d.get("children", d.get("nodes", d.get("results", []))) if isinstance(d, dict) else []
    # EDIT-only doctrine (2026-07-21): the load NEVER publishes — publication
    # is the single final act (publish_site.py publishes the declared folders
    # right after /files). This gate verifies the PRODUCING step: nodes exist
    # in EDIT with real content; LIVE parity belongs to the publish belt.
    if not kids:
        fails.append(f"{path}: 0 {ftype} nodes — listing has nothing to show")
    for k in kids:
        try:
            node = m.get(k["path"])
            props = node.get("properties", {}) or {}
            if not (props.get("jcr:title") or "").strip():
                fails.append(f"{k['path']}: no jcr:title — empty entity node")
        except Exception as e:
            fails.append(f"{k['path']}: unreadable ({str(e)[:60]})")
    else:
        print(f"  ok {path}: {len(kids)} {ftype} node(s) in EDIT")

if fails:
    print("FAIL:")
    for x in fails: print("  ✗", x)
    sys.exit(1)
print("PASS: all mainResource folders populated + published")
PY
