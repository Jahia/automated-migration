#!/usr/bin/env bash
# Static gate: enforce the non-negotiable CND modelling rules on every definition.cnd
# in the module (no running Jahia needed - it lints the source). Fails the build when:
#   1. a property named `title` / `jcr:title` is declared  -> extend `mix:title` instead
#   2. a custom tag/category field is declared             -> use `jmix:tagged` / `jmix:categorized`
#   3. `j:url` / `j:linknode` are declared                 -> injected by Jahia, never declare
#   4. a link/URL is stored as a plain `string` field      -> use `j:linkType (choicelist[linkTypeInitializer])`
#   5. an image/document URL is stored as a `string` field -> use a `weakreference` picker
# Usage: cnd-patterns.sh <project_path | path/to/one.cnd> [namespace]
#   - given a project path  -> lints every CND in src/ plus settings/definitions.cnd
#   - given a single .cnd    -> lints only that file (used by the per-component gate)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
target="${1:?project_path or .cnd file required}"
ns="${2:-}"
python3 - "$target" <<'PY'
import sys, os, re
target = sys.argv[1]
cnds = []
if target.endswith(".cnd") and os.path.isfile(target):
    cnds = [target]
    base = os.path.dirname(target) or "."
else:
    root = os.path.join(target, "src")
    if not os.path.isdir(root):
        root = target
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(".cnd"):
                cnds.append(os.path.join(dp, f))
    extra = os.path.join(target, "settings", "definitions.cnd")
    if os.path.isfile(extra):
        cnds.append(os.path.normpath(extra))
    base = target

PROP = re.compile(r"^\s*-\s*([A-Za-z0-9_:]+)\s*\((.*?)\)", )
TAG_NAMES = {"tags", "tag", "taglist", "j:taglist", "category", "categories", "keywords"}
INJECTED = {"j:url", "j:linknode"}
# URL *storage* fields only - a label/text/title/alt/caption ending is a legit i18n string
URL_SUFFIX = ("url",)            # ctaUrl, linkUrl, videoUrl, backgroundImageUrl, *ExternalUrl ...
LINK_SUFFIX = ("link",)          # link, ctaLink, logoLink, ctaPrimaryLink, ctaExposerLink ...
PLAIN_LINK = {"href", "linkto", "targeturl", "link"}
viol = []
for path in cnds:
    rel = os.path.relpath(path, base)
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            m = PROP.match(line)
            if not m:
                continue
            name, typ = m.group(1), m.group(2).lower()
            ln = name.lower()
            if ln in ("title", "jcr:title"):
                viol.append((rel, i, name, "declares a title property -> extend `mix:title` (gives i18n jcr:title shown in jContent)"))
            elif ln in TAG_NAMES:
                viol.append((rel, i, name, "custom tag/category field -> use `jmix:tagged` (j:tagList) and/or `jmix:categorized`"))
            elif ln in INJECTED:
                viol.append((rel, i, name, "injected by Jahia -> never declare; add only `j:linkType (choicelist[linkTypeInitializer])`"))
            elif "string" in typ and name != "j:linkType" and ln.endswith(URL_SUFFIX):
                viol.append((rel, i, name, "image/URL stored as string -> use a `weakreference` picker (image/file) or `j:linkType`"))
            elif "string" in typ and (ln in PLAIN_LINK or ln.endswith(LINK_SUFFIX)):
                viol.append((rel, i, name, "link stored as plain string -> use `j:linkType` (one per type) or child `ctaButton` nodes if the component has several links"))
if viol:
    print(f"FAIL: {len(viol)} CND pattern violation(s):", file=sys.stderr)
    for rel, i, name, msg in viol:
        print(f"  {rel}:{i}  `{name}`  {msg}")
    sys.exit(1)
print(f"PASS: {len(cnds)} CND file(s) clean (mix:title, jmix:tagged/categorized, linkTypeInitializer, weakref images)")
PY
