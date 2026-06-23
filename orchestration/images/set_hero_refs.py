#!/usr/bin/env python3
"""Set proper DAM image references on every sialp:pageHero (instead of URL strings).

The servlet-imported files have mismatched UUIDs across default/live workspaces, so
weakreferences to them break. This re-imports each page's hero via the MCP
media.upload.url tool (which creates ONE publishable DAM node with a consistent UUID),
publishes it, sets the pageHero.backgroundImage WEAKREFERENCE to it, and publishes the
hero. The PageHero view prefers backgroundImage (buildNodeUrl) over backgroundImageUrl.

Usage: python3 orchestration/images/set_hero_refs.py   (run from repo root)
"""
import json, os, sys, urllib.request, urllib.parse

PROJECT = sys.argv[1] if len(sys.argv) > 1 else "sial-paris"
SITE = sys.argv[2] if len(sys.argv) > 2 else PROJECT
NS = sys.argv[3] if len(sys.argv) > 3 else "sialp"

def env():
    u, h, tok = "root:root", "http://localhost:8080", ""
    p = f"projects/{PROJECT}/.env"
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line.startswith("JAHIA_USER="): u = line.split("=", 1)[1]
            elif line.startswith("JAHIA_HOST="): h = line.split("=", 1)[1]
            elif line.startswith("JAHIA_MCP_TOKEN="): tok = line.split("=", 1)[1]
    return u, h, tok

USER, HOST, TOKEN = env()
import base64
AUTH = "Basic " + base64.b64encode(USER.encode()).decode()

def mcp(name, args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}}).encode()
    req = urllib.request.Request(HOST + "/modules/mcp", body,
        {"Content-Type": "application/json", "Authorization": "APIToken " + TOKEN})
    d = json.load(urllib.request.urlopen(req))
    txt = d.get("result", {}).get("content", [{}])[0].get("text", "")
    try: return json.loads(txt)
    except Exception: return {"_raw": txt}

def gql(query):
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(HOST + "/modules/graphql", body,
        {"Content-Type": "application/json", "Authorization": AUTH, "Origin": HOST})
    return json.load(urllib.request.urlopen(req))

# 1. all pageHero nodes under the site (path) via JCR-SQL2
q = ("{ jcr(workspace: EDIT) { result: nodesByQuery(query: \"SELECT * FROM ["+NS+":pageHero] "
     "WHERE ISDESCENDANTNODE('/sites/"+SITE+"/home')\") { nodes { path } } } }")
heroes = [n["path"] for n in gql(q)["data"]["jcr"]["result"]["nodes"]]
print(f"found {len(heroes)} pageHero nodes")

man = json.load(open(f"orchestration/images/{PROJECT}.json"))
base, pages = man["base"], man["pages"]

def page_key(hero_path):
    # /sites/<site>/home/<key>/main/hero  OR /sites/<site>/home (home)
    p = hero_path.replace(f"/sites/{SITE}/home", "").strip("/")
    # drop trailing /main/hero (or /<list>/<hero>)
    parts = p.split("/")
    # remove last two segments (list + hero node) if present
    if len(parts) >= 2:
        key = "/".join(parts[:-2]) if len(parts) > 2 else ""
    else:
        key = ""
    return key or "home"

ok = skip = fail = 0
for hero in heroes:
    key = page_key(hero)
    entries = pages.get(key, [])
    hero_img = next((e for e in entries if e.get("role") == "hero"), entries[0] if entries else None)
    if not hero_img:
        print(f"  SKIP {key}: no hero source in manifest"); skip += 1; continue
    src = hero_img["src"] if hero_img["src"].startswith("http") else base + hero_img["src"]
    folder = "migrated/" + key
    try:
        up = mcp("media.upload.url", {"siteKey": SITE, "sourceUrl": src,
                                      "folder": folder, "fileName": "hero-dam.jpg"})
        uuid = up.get("identifier")
        if not uuid:
            print(f"  FAIL {key}: upload -> {str(up)[:120]}"); fail += 1; continue
        img_path = up["path"]
        gql(f'mutation{{jcr{{mutateNode(pathOrId:"{img_path}"){{publish}}}}}}')
        r = gql(f'mutation{{jcr{{mutateNode(pathOrId:"{hero}"){{mutateProperty(name:"backgroundImage")'
                f'{{setValue(type:WEAKREFERENCE,value:"{uuid}")}}}}}}}}')
        set_ok = r.get("data", {}).get("jcr", {}).get("mutateNode", {}).get("mutateProperty", {}).get("setValue")
        gql(f'mutation{{jcr{{mutateNode(pathOrId:"{hero}"){{publish}}}}}}')
        print(f"  OK   {key}: {'set' if set_ok else 'SET-FAIL'} -> hero-dam.jpg ({uuid[:8]})")
        ok += 1
    except Exception as e:
        print(f"  FAIL {key}: {e}"); fail += 1

print(f"\n{ok} ok, {skip} skipped, {fail} failed")
