#!/usr/bin/env bash
# crawl.sh — Page inventory gate.
#
# Verifies that the site was crawled and every page has a cached HTML file.
# Supports MAX_PAGES env var for testing on a subset.
#
# Usage: crawl.sh <project_path>
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
out="$proj/workflow-output"

# 1. page-inventory.json exists and is non-empty
[ -s "$out/page-inventory.json" ] || fail "crawl: $out/page-inventory.json missing or empty"

# 2. Parse and validate
python3 - "$proj" <<'PY'
import json, os, sys

proj = sys.argv[1]
path = f"{proj}/workflow-output/page-inventory.json"
try:
    data = json.load(open(path))
except Exception as e:
    print(f"FAIL: cannot parse page-inventory.json: {e}"); sys.exit(1)

pages = data.get("pages", [])
if not pages:
    print("FAIL: page-inventory.json has 0 pages"); sys.exit(1)

# 3. Every page must have a cached file
missing = []
for p in pages:
    cached = p.get("cachedAt", "")
    if not cached:
        missing.append(f"  {p.get('slug','?')}: no cachedAt field")
    elif not os.path.isfile(os.path.join(proj, cached)):
        missing.append(f"  {p.get('slug','?')}: cached file not found: {cached}")

if missing:
    print("FAIL: pages with missing cache:")
    for m in missing: print(m)
    sys.exit(1)

# 4. home must be present
slugs = [p.get("slug","") for p in pages]
if "home" not in slugs:
    print("FAIL: 'home' page not found in inventory"); sys.exit(1)

# 5. Report
failed = data.get("failedPages", [])
max_pages = data.get("maxPages", "unlimited")
assets = data.get("assetsDownloaded", 0)
print(f"  pages: {len(pages)} crawled (max={max_pages})")
print(f"  assets: {assets} downloaded")
print(f"  failed: {len(failed)}")
if failed:
    for f in failed[:5]: print(f"    - {f.get('url','?')} ({f.get('error','?')})")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "crawl: inventory validation failed"
pass "crawl: page-inventory.json valid"
