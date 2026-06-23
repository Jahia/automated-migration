#!/usr/bin/env bash
# Artifact probe: a required output file exists (and optionally is clean).
# Usage: artifact.sh <file> [forbidden_regex]
#   Passes if <file> exists and is non-empty.
#   If <forbidden_regex> is given, fails when that pattern is found in the file
#   (e.g. a review report that must contain zero "critical" findings).
set -euo pipefail
f="${1:?file path required}"
test -s "$f" || { echo "FAIL: $f missing or empty" >&2; exit 1; }
if [ "${2:-}" != "" ]; then
  if grep -qiE "$2" "$f"; then
    echo "FAIL: forbidden pattern '$2' found in $f" >&2
    exit 1
  fi
fi
echo "PASS: $f"
