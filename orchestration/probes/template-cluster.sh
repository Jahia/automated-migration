#!/usr/bin/env bash
# template-cluster.sh — Template clustering output gate.
#
# Verifies that template-clusters.json exists and has valid structure.
# Does NOT make clustering decisions — that's the LLM's job.
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

# 1. At least 1 cluster
if not cluster_list:
    print("FAIL: 0 clusters found"); sys.exit(1)

# 2. Every page in at least 1 cluster
assigned = set()
for c in cluster_list:
    assigned.update(c.get("pages", []))

missing = all_slugs - assigned
if missing:
    print(f"FAIL: pages not in any cluster: {missing}"); sys.exit(1)

# 3. CrossCutting must exist
if not cross_cutting:
    print("WARNING: no cross-cutting components identified")

# 4. Report
print(f"  clusters: {len(cluster_list)}")
for c in cluster_list:
    print(f"    {c.get('clusterId', '?')}: {len(c.get('pages', []))} pages")
print(f"  crossCutting: {', '.join(cross_cutting.keys()) if cross_cutting else 'none'}")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "template-cluster: validation failed"
pass "template-cluster: output valid"
