#!/usr/bin/env bash
# template-cluster.sh — Template clustering gate.
#
# Verifies that every page is assigned to exactly one template cluster
# or to a cross-cutting region (header/footer/topbar).
#
# Usage: template-cluster.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
out="$proj/workflow-output"

[ -s "$out/template-clusters.json" ] || fail "template-cluster: $out/template-clusters.json missing or empty"
[ -s "$out/page-inventory.json" ] || fail "template-cluster: $out/page-inventory.json missing (run crawl first)"

python3 - "$proj" <<'PY'
import json, sys

proj = sys.argv[1]
clusters = json.load(open(f"{proj}/workflow-output/template-clusters.json"))
inventory = json.load(open(f"{proj}/workflow-output/page-inventory.json"))

all_slugs = {p["slug"] for p in inventory.get("pages", [])}
cluster_list = clusters.get("clusters", [])
cross_cutting = clusters.get("crossCutting", {})
unclustered = clusters.get("unclustered", [])

# 1. At least 1 cluster
if not cluster_list:
    print("FAIL: 0 clusters found"); sys.exit(1)

# 2. Every page in exactly 1 cluster
assigned = set()
for c in cluster_list:
    pages = set(c.get("pages", []))
    overlap = assigned & pages
    if overlap:
        print(f"FAIL: pages assigned to multiple clusters: {overlap}"); sys.exit(1)
    assigned |= pages

missing = all_slugs - assigned
if missing:
    # Pages in crossCutting are OK
    cc_pages = set()
    for v in cross_cutting.values():
        if isinstance(v, dict) and v.get("pages") == "all":
            cc_pages = all_slugs
        elif isinstance(v, dict):
            cc_pages |= set(v.get("pages", []))
    truly_missing = missing - cc_pages
    if truly_missing:
        print(f"FAIL: pages not in any cluster or crossCutting: {truly_missing}"); sys.exit(1)

# 3. CrossCutting must have header + footer
for region in ["header", "footer"]:
    if region not in cross_cutting:
        print(f"FAIL: crossCutting missing '{region}'"); sys.exit(1)

# 4. Report
print(f"  clusters: {len(cluster_list)}")
for c in cluster_list:
    print(f"    {c['clusterId']}: {len(c.get('pages',[]))} pages")
print(f"  crossCutting: {', '.join(cross_cutting.keys())}")
if unclustered:
    print(f"  WARNING: {len(unclustered)} unclustered pages: {unclustered}")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "template-cluster: validation failed"
pass "template-cluster: all pages assigned, crossCutting regions present"
