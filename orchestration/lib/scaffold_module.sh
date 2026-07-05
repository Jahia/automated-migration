#!/usr/bin/env bash
# scaffold_module.sh — HEADLESS Jahia JS module scaffold (QUALITY-PLAN P1.3).
#
# `npm init @jahia/module` is @clack/prompts-driven (TTY required) and refuses
# existing directories — unusable from the orchestrator, and expect-driving its
# per-frame ANSI redraws proved brittle. This reproduces the tool's EXACT logic
# (read @jahia/create-module/index.js: copy templates `module` + `template-set`
# with $MODULE/$NAMESPACE/$VERSION templating, rename dot/ → .) from the
# OFFICIAL npm package — same templates, byte-identical output, no TTY, and it
# composes with our layout (module files land INSIDE projects/<p>/ next to
# .reference/ and workflow-output/, like every v1 module).
#
# The scaffold's default CND namespace ($MODULE minus hyphens) is a placeholder:
# merge_cnd.py replaces settings/definitions.cnd with the analyze-phase CND.
#
# Usage: scaffold_module.sh <project> [module-name] [--version X.Y.Z] [--force]
#   e.g. scaffold_module.sh acquia-drupal
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../probes/_lib.sh
source "$HERE/../probes/_lib.sh"
CM_VERSION="1.2.0"
FORCE=0
positional=()
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --version) CM_VERSION="${2:?--version needs a value}"; shift 2 ;;
    *) positional+=("$1"); shift ;;
  esac
done
project="${positional[0]:?project required (e.g. acquia-drupal)}"
module="${positional[1]:-$project}"
load_env ""
require_node 20

dest="projects/$project"
[ -d "$dest" ] || mkdir -p "$dest"
if [ -f "$dest/package.json" ] && [ "$FORCE" != 1 ]; then
  echo "[scaffold] $dest/package.json already exists — module already scaffolded (use --force to overwrite)"
  exit 0
fi

# official package, cached (deterministic: pinned version)
cache="orchestration/.cache"
mkdir -p "$cache"
pkgdir="$cache/create-module-$CM_VERSION"
if [ ! -d "$pkgdir/templates" ]; then
  tmp="$(mktemp -d)"
  ( cd "$tmp" && npm pack "@jahia/create-module@$CM_VERSION" --silent >/dev/null \
      && tar xf jahia-create-module-*.tgz )
  rm -rf "$pkgdir"
  mkdir -p "$pkgdir"
  cp -R "$tmp/package/templates" "$pkgdir/templates"
  node -e "console.log(require('$tmp/package/package.json').version)" > "$pkgdir/VERSION"
  rm -rf "$tmp"
fi
version="$(cat "$pkgdir/VERSION")"
namespace="${module//-/}"   # a CND namespace cannot contain hyphens (tool rule)

# copy templates `module` then `template-set` (the tool's "empty template set"
# choice), templating $MODULE/$NAMESPACE/$VERSION, renaming dot/ → .
python3 - "$pkgdir/templates" "$dest" "$module" "$namespace" "$version" <<'EOF'
import os, shutil, sys
tpl_root, dest, module, namespace, version = sys.argv[1:6]
count = 0
for tpl in ("module", "template-set"):
    root = os.path.join(tpl_root, tpl)
    for dp, _, fs in os.walk(root):
        for fn in fs:
            src = os.path.join(dp, fn)
            rel = os.path.relpath(src, root)
            if rel.startswith("dot" + os.sep):
                rel = "." + rel[len("dot" + os.sep):]   # dot/env -> .env (tool's renameDot)
            rel = rel.replace("$MODULE", module).replace("$NAMESPACE", namespace)
            out = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if fn.endswith(".png"):
                shutil.copyfile(src, out)
            else:
                s = open(src, encoding="utf-8").read()
                s = (s.replace("$MODULE", module)
                       .replace("$NAMESPACE", namespace)
                       .replace("$VERSION", version))
                open(out, "w", encoding="utf-8").write(s)
            count += 1
print(f"[scaffold] {count} files -> {dest} (module={module}, ns placeholder={namespace}, create-module {version})")
EOF

# module .env from the repo-root env truth (never committed — **/.env ignored)
HOST="${JAHIA_URL:-${JAHIA_HOST:-http://localhost:8080}}"
USERPASS="${JAHIA_USER:-root}"
[[ "$USERPASS" == *:* ]] || USERPASS="$USERPASS:${JAHIA_PASS:-root}"
cat > "$dest/.env" <<ENV
JAHIA_USER=$USERPASS
JAHIA_HOST=${HOST%/}
ENV

# yarn 4 refuses to install inside another project's tree without a local
# lockfile marking the boundary (the repo root is not a workspace parent)
[ -f "$dest/yarn.lock" ] || touch "$dest/yarn.lock"
( cd "$dest" && yarn install 2>&1 | tail -3 ) || fail "yarn install failed in $dest"

for f in package.json vite.config.mjs settings/definitions.cnd src/templates/Layout.tsx; do
  [ -e "$dest/$f" ] || fail "scaffold incomplete: $f missing"
done
head -1 "$dest/settings/definitions.cnd" | grep -q "^<" \
  || fail "scaffolded definitions.cnd lacks the namespace header (module would fail to install)"
pass "headless scaffold complete: $dest (yarn install OK)"
