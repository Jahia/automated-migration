#!/usr/bin/env bash
# extract-blocks.sh — HTML block extraction gate.
#
# Verifies that html-blocks.json was produced with real blocks from every page.
# Purely format validation — no semantic decisions.
#
# Usage: extract-blocks.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
out="$proj/workflow-output"

[ -s "$out/html-blocks.json" ] || fail "extract-blocks: $out/html-blocks.json missing or empty"
[ -s "$out/page-inventory.json" ] || fail "extract-blocks: $out/page-inventory.json missing (run crawl first)"

python3 - "$proj" <<'PY'
import json, sys

proj = sys.argv[1]
blocks_data = json.load(open(f"{proj}/workflow-output/html-blocks.json"))
inventory = json.load(open(f"{proj}/workflow-output/page-inventory.json"))

pages_in_inv = {p["slug"] for p in inventory.get("pages", [])}
pages_in_blocks = {p["slug"] for p in blocks_data.get("pages", [])}
total_blocks = blocks_data.get("totalBlocks", 0)

# 1. Every page must have blocks
missing = pages_in_inv - pages_in_blocks
if missing:
    print(f"FAIL: pages missing from html-blocks.json: {missing}"); sys.exit(1)

# 2. Must have blocks
if total_blocks == 0:
    print("FAIL: 0 blocks extracted"); sys.exit(1)

# 3. Each page must have at least 1 block
for page in blocks_data.get("pages", []):
    if not page.get("blocks"):
        print(f"FAIL: page '{page['slug']}' has 0 blocks"); sys.exit(1)

# 4. Report
print(f"  pages: {len(pages_in_blocks)}")
print(f"  total blocks: {total_blocks}")
for page in blocks_data.get("pages", [])[:5]:
    b = page["blocks"]
    img = sum(1 for x in b if x.get("hasImage"))
    link = sum(1 for x in b if x.get("hasLink"))
    head = sum(1 for x in b if x.get("hasHeading"))
    print(f"    {page['slug']:30s} blocks={len(b):4d}  img={img:3d}  links={link:3d}  headings={head:3d}")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "extract-blocks: validation failed"
pass "extract-blocks: html-blocks.json valid"
