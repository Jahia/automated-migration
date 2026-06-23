#!/usr/bin/env bash
# Step 9 probe: every page's LIVE <main> renders real content (>400 chars).
# A lone hero stub counts as empty. This is the per-page checklist the
# Conductor used; it is the step most prone to a false "completed".
# Usage: content.sh <project_path> <site_key> <lang> <pages>
#   <pages> is either a comma-separated list of relative paths, or @<file>
#   pointing at a newline-separated sitemap (blank lines and #comments ignored).
#   page "home" maps to /sites/<site>/home; "le-salon/x" -> /sites/<site>/home/le-salon/x
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
site="${2:?site_key required}"
lang="${3:?lang required}"
pages="${4:?comma-separated pages or @sitemap-file required}"
min_chars="${5:-400}"
load_env "$proj"
# @file -> read newline-separated paths, drop blanks/comments, join with commas
case "$pages" in
  @*) file="${pages#@}"
      [ -f "$file" ] || fail "sitemap file not found: $file"
      pages="$(grep -vE '^[[:space:]]*(#|$)' "$file" | tr -d '\r' | tr '\n' ',' | sed 's/,$//')"
      [ -n "$pages" ] || fail "sitemap file $file has no page paths" ;;
esac
python3 - "$JAHIA_HOST" "$JAHIA_USER" "$site" "$lang" "$pages" "$min_chars" <<'PY'
import sys, subprocess, re
host, user, site, lang, pages = sys.argv[1:6]
min_chars = int(sys.argv[6])
bad = []
for p in pages.split(','):
    p = p.strip()
    if not p:
        continue
    node = f"/sites/{site}/home" if p == "home" else f"/sites/{site}/home/{p}"
    url = f"{host}/cms/render/live/{lang}{node}.html"
    html = subprocess.run(["curl", "-s", "-u", user, url],
                          capture_output=True, text=True).stdout
    m = re.search(r"<main[^>]*>(.*?)</main>", html, re.S | re.I)
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
    ok = len(txt) >= min_chars
    print(f"  {p}: {len(txt)} chars (min {min_chars}) {'OK' if ok else 'THIN'}")
    if not ok:
        bad.append(p)
if bad:
    print("FAIL: empty/stub pages:", ", ".join(bad))
    sys.exit(1)
print("PASS: all pages have live content")
PY
