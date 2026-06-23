# Shared helpers for migration verification probes.
# Sourced by every probe. Never executed directly.
#
# Probes are the hard gate: the orchestration loop runs whatever a step's agent
# returns in `commands_requested` (with cwd = jahiaMigration repo root) and a
# step only passes when every command exits 0. These scripts encode the
# verification probes the in-repo Conductor used to run by hand.

# load_env <project_path>
# Loads JAHIA_USER / JAHIA_HOST from <project_path>/.env if present, else
# falls back to local-dev defaults. Mirrors how `yarn jahia-deploy` reads .env.
load_env() {
  local proj="${1:-}"
  if [ -n "$proj" ] && [ -f "$proj/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$proj/.env"
    set +a
  fi
  : "${JAHIA_USER:=root:root}"
  : "${JAHIA_HOST:=http://localhost:8080}"
  export JAHIA_USER JAHIA_HOST
}

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; exit 0; }

# require_node <min_major> - fail early with a clear message if Node is too old.
# The Jahia JS modules use Vite + @jahia/vite-plugin which needs Node >= 20
# (styleText from node:util). The orchestration loop's opencode must run under
# Node >= 22 (v22.21.0), or every build/deploy probe fails cryptically.
require_node() {
  local min="${1:-20}" v major
  v="$(node -v 2>/dev/null || true)"
  major="${v#v}"; major="${major%%.*}"
  [ -n "$major" ] || fail "Node.js not on PATH (need >= $min; use Node 22 via mise/nvm)"
  [ "$major" -ge "$min" ] || fail "Node $v too old - this module needs Node >= $min (v22.21.0). Run the loop/opencode under Node 22."
}
