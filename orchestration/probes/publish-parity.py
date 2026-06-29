#!/usr/bin/env python3
"""publish-parity.py — assert published content has no dangling references in LIVE.

Catches the two publish failures that recur in migrations:
  1. A content node references an asset/target (weakreference: image, logo,
     j:linknode, j:defaultCategory, ...) whose target node is NOT in the LIVE
     workspace — i.e. the page was published but the DAM image / linked node /
     category was not. The reference resolves to null and the asset silently
     never renders.
  2. A content node exists in EDIT for a language but its translation is absent
     in LIVE for that language — i.e. published without `languages:[...]`, so the
     translation never reached live.

Invoked by publish-parity.sh (passes JAHIA_HOST / JAHIA_USER / siteKey / langs).
Exit 0 = clean, 1 = dangling references / missing translations found.
"""
import base64, json, os, sys, urllib.request

HOST = os.environ.get("JAHIA_HOST", "http://localhost:8080").rstrip("/")
USER = os.environ.get("JAHIA_USER", "root:root")
SITE = sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: publish-parity.py <siteKey> [langs csv]")
LANGS = (sys.argv[2].split(",") if len(sys.argv) > 2 else ["en"])
GQL = f"{HOST}/modules/graphql"
AUTH = "Basic " + base64.b64encode(USER.encode()).decode()


def gql(query):
    req = urllib.request.Request(
        GQL, data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "Origin": HOST, "Authorization": AUTH})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def q_nodes(workspace, sql):
    d = gql(f'{{jcr(workspace:{workspace}){{nodesByQuery(query:"{sql}"){{nodes{{'
            f'uuid path properties{{name values definition{{requiredType}}}}}}}}}}}}')
    if d.get("errors"):
        sys.exit(f"FAIL: publish-parity GraphQL error: {json.dumps(d['errors'])[:300]}")
    return d["data"]["jcr"]["nodesByQuery"]["nodes"]


esc = lambda p: p.replace("'", "''")
SCOPE = f"isdescendantnode('/sites/{esc(SITE)}')"

# ---- 1. collect weakreference targets from LIVE content ----
live = q_nodes("LIVE", f"select * from [jnt:content] where {SCOPE}")
refs = []  # (path, prop, uuid)
for n in live:
    for p in n.get("properties", []):
        if (p.get("definition") or {}).get("requiredType") == "WEAKREFERENCE":
            for v in (p.get("values") or []):
                if v and len(v) >= 32 and "-" in v:  # looks like a uuid
                    refs.append((n["path"], p["name"], v))

uuids = sorted({u for _, _, u in refs})
missing = set()
# check existence in LIVE, chunked with aliases
for i in range(0, len(uuids), 40):
    chunk = uuids[i:i + 40]
    body = " ".join(f'a{j}:nodeById(uuid:"{u}"){{uuid}}' for j, u in enumerate(chunk))
    d = gql(f"{{jcr(workspace:LIVE){{{body}}}}}")
    data = (d.get("data") or {}).get("jcr") or {}
    for j, u in enumerate(chunk):
        if not data.get(f"a{j}"):
            missing.add(u)

broken = [(path, prop, u) for (path, prop, u) in refs if u in missing]

# ---- 2. translation presence per language (EDIT has it, LIVE missing) ----
trans_gaps = []
for lang in LANGS:
    edit = q_nodes("EDIT", f"select * from [jmix:mainResource] where {SCOPE}")
    for n in edit:
        # node has a jcr:title in this lang in EDIT?
        d = gql(f'{{e:jcr(workspace:EDIT){{nodeById(uuid:"{n["uuid"]}"){{p:property(name:"jcr:title",language:"{lang}"){{value}}}}}}'
                f' l:jcr(workspace:LIVE){{nodeById(uuid:"{n["uuid"]}"){{p:property(name:"jcr:title",language:"{lang}"){{value}}}}}}}}')
        data = d.get("data") or {}
        e = (((data.get("e") or {}).get("nodeById") or {}).get("p") or {})
        liveNode = ((data.get("l") or {}).get("nodeById"))
        if e.get("value") and liveNode is None:
            trans_gaps.append((n["path"], lang))

# ---- report ----
print(json.dumps({
    "live_content_nodes": len(live),
    "weakrefs_checked": len(refs),
    "broken_refs": [{"node": p, "prop": pr, "missing_uuid": u} for p, pr, u in broken][:30],
    "translation_gaps": [{"node": p, "lang": l} for p, l in trans_gaps][:30],
}, indent=1, ensure_ascii=False))

if broken or trans_gaps:
    print(f"FAIL: publish-parity — {len(broken)} dangling weakref(s) + "
          f"{len(trans_gaps)} missing translation(s) in LIVE", file=sys.stderr)
    sys.exit(1)
print("PASS: publish-parity — all weakref targets resolve in LIVE; no missing translations")
