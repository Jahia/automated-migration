#!/usr/bin/env bash
# content.sh — create-content gate, grounded in REALITY (the actual source), not
# an arbitrary threshold.
#
# The old check ("every page's <main> has >400 chars of text") was a fake proxy:
# a page of placeholder filler passes it, and it says nothing about whether the
# migration reproduces the real site. This gate instead measures the page against
# the actual cached source and the real JCR state:
#
#   1. content-fidelity — the live JCR actually has it: image weakrefs SET,
#      jmix:mainResource listings EXIST, nav/footer shell populated, EN present,
#      no test/debris nodes. (queries the running instance)
#   2. fidelity-all     — render the LIVE page AND the real reference (wget crawl
#      cache) in headless Chromium and compare: missing sections, listing/card
#      shortfall, missing facets, image shortfall. Saves a reference-vs-local
#      screenshot pair per page. (compares to the ACTUAL source page)
#
# Usage: content.sh <project_path> <site_key> <lang> <pages|@sitemap>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
site="${2:?site_key required}"
lang="${3:?lang required}"
pages="${4:?comma-separated pages or @sitemap-file required}"   # @file or csv; passed through to fidelity-all
load_env "$proj"

# 1. Real JCR state: images / listings / shell / EN / no debris.
echo "── content-fidelity (live JCR: images / listings / shell / EN / debris):"
bash "$HERE/content-fidelity.sh" "$proj" "$site" "fr,en"

# 2. Reference comparison: does each live page actually reproduce the real source
#    page (sections / cards / images), rendered both sides in Chromium?
echo "── fidelity-all (live page vs the real cached reference, per page):"
bash "$HERE/fidelity-all.sh" "$proj" "$site" "$lang" "$pages"

pass "content: matches the live JCR reality AND the real reference source (no char-count proxy)"
