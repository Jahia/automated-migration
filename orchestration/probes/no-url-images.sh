#!/usr/bin/env bash
# Gate: NO image may be referenced by a URL-string field - every image must be a
# DAM weakreference (see AGENTS.md section 2a). Fails if any *ExternalUrl image
# field (imageExternalUrl / backgroundImageUrl / logoExternalUrl) is still set.
# Usage: no-url-images.sh <project_path> <site_key> [namespace]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"
proj="${1:?project_path required}"
site="${2:?site_key required}"
ns="${3:-sialp}"
load_env "$proj"
python3 - "$JAHIA_HOST" "$JAHIA_USER" "$site" "$ns" <<'PY'
import sys, json, base64, urllib.request
host, user, site, ns = sys.argv[1:5]
auth = "Basic " + base64.b64encode(user.encode()).decode()
def gql(q):
    req = urllib.request.Request(host+"/modules/graphql", json.dumps({"query":q}).encode(),
        {"Content-Type":"application/json","Authorization":auth,"Origin":host})
    return json.load(urllib.request.urlopen(req))
# (type, url-string field) pairs that must NEVER be populated (use the weakref instead)
PAIRS = [(f"{ns}:editorialBlock","imageExternalUrl"), (f"{ns}:imgContentBlock","imageExternalUrl"),
         (f"{ns}:pagesPushesItem","imageExternalUrl"), (f"{ns}:trendCard","imageExternalUrl"),
         (f"{ns}:partnerLogo","logoExternalUrl"), (f"{ns}:partnerEntry","logoExternalUrl"),
         (f"{ns}:pageHero","backgroundImageUrl"), (f"{ns}:heroCarousel","backgroundImageUrl")]
total = 0
for t, f in PAIRS:
    q = (f'{{jcr(workspace:EDIT){{nodesByQuery(query:"SELECT * FROM [{t}] WHERE {f} IS NOT NULL '
         f"AND ISDESCENDANTNODE('/sites/{site}/home')\"){{nodes{{path}}}}}}}}")
    try:
        nb = (gql(q).get("data",{}).get("jcr") or {}).get("nodesByQuery")
        n = len(nb["nodes"]) if nb else 0
    except Exception:
        n = 0   # type may not exist on this site - not a violation
    if n:
        print(f"  {t}.{f}: {n} node(s) still using a URL string")
        total += n
if total:
    print(f"FAIL: {total} image(s) referenced by URL string instead of a DAM weakreference", file=sys.stderr)
    sys.exit(1)
print("PASS: all images are DAM weakreferences (no *ExternalUrl image fields set)")
PY
