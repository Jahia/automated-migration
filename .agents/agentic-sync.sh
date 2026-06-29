#!/usr/bin/env bash
# agentic-sync.sh — diff jahiaMigration's dev skills against the upstream
# @jahia/agentic reference harness (https://github.com/Jahia/agentic).
#
# jahiaMigration's reference dev/integration skills live in .agents/skills/dev/
# (the numbered 00-13 skills are the migration WORKFLOW; dev/ is the underlying
# Jahia dev knowledge that tracks agentic). Run this periodically to stay in
# sync; update AGENTIC-SYNC.md with the new version + decisions afterward.
#
# Usage: .agents/agentic-sync.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOC="$HERE/skills/dev"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
gh repo clone Jahia/agentic "$TMP/a" -- --depth 1 >/dev/null 2>&1 || { echo "clone failed (need gh auth)"; exit 1; }
AG="$TMP/a/src/harness/skills"
ver="$(node -e "console.log(require('$TMP/a/package.json').version)" 2>/dev/null || echo '?')"

echo "Upstream @jahia/agentic: v$ver   (local: .agents/skills/dev/)"
echo
echo "## MISSING in dev/ (in agentic, not here)"
for d in "$AG"/*/; do n=$(basename "$d"); [ -d "$LOC/$n" ] || echo "  + $n"; done
echo
echo "## CHANGED (in both, content differs)"
for d in "$AG"/*/; do n=$(basename "$d"); f="$LOC/$n/SKILL.md"
  [ -f "$f" ] && ! diff -q "$d/SKILL.md" "$f" >/dev/null 2>&1 && \
    printf "  ~ %-30s agentic=%s local=%s\n" "$n" "$(wc -l <"$d/SKILL.md"|tr -d ' ')" "$(wc -l <"$f"|tr -d ' ')"; done
echo
echo "## IDENTICAL (synced)"
for d in "$AG"/*/; do n=$(basename "$d"); f="$LOC/$n/SKILL.md"
  [ -f "$f" ] && diff -q "$d/SKILL.md" "$f" >/dev/null 2>&1 && echo "  = $n"; done
echo
echo "NOTE: create-view / create-page-template / debug / review are intentionally"
echo "covered by jahiaMigration's numbered migration skills (07,08,10,11,support-create-view)."
echo "Record version + decisions in .agents/AGENTIC-SYNC.md after reviewing."
