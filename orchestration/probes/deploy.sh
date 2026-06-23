#!/usr/bin/env bash
# Deploy probe: module builds and deploys to the running Jahia instance.
# Usage: deploy.sh <project_path>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
require_node 20
( cd "$proj" && yarn build && yarn jahia-deploy )
pass "build + jahia-deploy succeeded for $proj"
