#!/usr/bin/env bash
# Build probe: module compiles clean.
# Usage: build.sh <project_path>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
require_node 20
test -f "$proj/package.json" || fail "no package.json in $proj"
( cd "$proj" && yarn build )
pass "yarn build clean in $proj"
