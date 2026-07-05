# Shared helpers for migration verification probes.
# Sourced by every probe. Never executed directly.
#
# Probes are the hard gate: the orchestration loop runs whatever a step's agent
# returns in `commands_requested` (with cwd = jahiaMigration repo root) and a
# step only passes when every command exits 0. These scripts encode the
# verification probes the in-repo Conductor used to run by hand.

# _env_defaults <file>
# Exports KEY=VALUE lines from <file> for keys NOT already set — the repo-root
# .env.local provides defaults, it never overrides the caller's environment or
# a project .env. Comments and blank lines are ignored.
_env_defaults() {
  local f="$1" line key
  [ -f "$f" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    key="${line%%=*}"
    case "$key" in ''|*[!A-Za-z0-9_]*) continue ;; esac
    [ -n "${!key:-}" ] || export "$key=${line#*=}"
  done < "$f"
}

# load_env <project_path>
# Loads JAHIA_* from <project_path>/.env if present, then fills the gaps from
# the repo-root .env.local (copy .env.example), then local-dev defaults.
# Exports JAHIA_HOST (= JAHIA_URL) and the combined JAHIA_USER=user:pass form
# the probes pass to curl -u. Mirrors how `yarn jahia-deploy` reads .env.
load_env() {
  local proj="${1:-}"
  if [ -n "$proj" ] && [ -f "$proj/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$proj/.env"
    set +a
  fi
  _env_defaults "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.env.local"
  : "${JAHIA_URL:=${JAHIA_HOST:-http://localhost:8080}}"
  : "${JAHIA_HOST:=$JAHIA_URL}"
  if [ -n "${JAHIA_PASS:-}" ] && [[ "${JAHIA_USER:-root}" != *:* ]]; then
    JAHIA_USER="${JAHIA_USER:-root}:$JAHIA_PASS"
  fi
  : "${JAHIA_USER:=root:root}"
  : "${JAHIA_TOOLS_ORIGIN:=$JAHIA_URL}"
  export JAHIA_URL JAHIA_HOST JAHIA_USER JAHIA_TOOLS_ORIGIN
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
