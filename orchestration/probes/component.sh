#!/usr/bin/env bash
# Component probe: a named component exists (view) and the module builds.
# Usage: component.sh <project_path> <ComponentNameOrFile>
# Verifies the component view file exists, then that the module compiles.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
name="${2:?component name required}"
require_node 20
hit=$(find "$proj/src" -iname "*${name}*" 2>/dev/null | head -1)
[ -n "$hit" ] || fail "no source file matching '$name' under $proj/src"
( cd "$proj" && yarn build )
pass "component '$name' present ($hit); build clean"
