#!/usr/bin/env python3
"""Canonical image-reference fixer: make every content image a proper DAM weakreference.

THE PATTERN (use for every migration): images must be imported into Jahia's DAM as a
node with a CONSISTENT cross-workspace UUID (via MCP media.upload.url) and referenced
through a WEAKREFERENCE field (image/logo/photo/backgroundImage), NEVER a URL string.
The *ExternalUrl string fields are content-editor anti-patterns and break editing.

This finds every content node whose image is set via a URL-string field, (re)imports
the image properly, sets the matching weakreference, publishes, and CLEARS the
url-string so Content Editor shows only the picked asset. Handles BOTH images already
in Jahia (/files/.../<site>/files/...) and hot-linked external CDN URLs (https).

Usage: python3 orchestration/images/set_image_refs.py [project] [siteKey]
       defaults: project=sial-paris, siteKey=project
"""
import json, sys, os, base64, urllib.request

PROJECT = sys.argv[1] if len(sys.argv) > 1 else "sial-paris"
SITE = sys.argv[2] if len(sys.argv) > 2 else PROJECT
NS = sys.argv[3] if len(sys.argv) > 3 else "sialp"

def env():
    u, h, tok = "root:root", "http://localhost:8080", ""
    for line in open(f"projects/{PROJECT}/.env"):
        line = line.strip()
        if line.startswith("JAHIA_USER="): u = line.split("=", 1)[1]
        elif line.startswith("JAHIA_HOST="): h = line.split("=", 1)[1]
        elif line.startswith("JAHIA_MCP_TOKEN="): tok = line.split("=", 1)[1]
    return u, h, tok
USER, HOST, TOKEN = env()
AUTH = "Basic " + base64.b64encode(USER.encode()).decode()
DAMFOLDER = "migrated/imported-media"   # shared folder for re-imported / external images

def mcp(name, args):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}}).encode()
    req = urllib.request.Request(HOST+"/modules/mcp", body, {"Content-Type":"application/json","Authorization":"APIToken "+TOKEN})
    txt = json.load(urllib.request.urlopen(req)).get("result",{}).get("content",[{}])[0].get("text","")
    try: return json.loads(txt)
    except Exception: return {"_raw": txt}

def gql(q):
    body = json.dumps({"query": q}).encode()
    req = urllib.request.Request(HOST+"/modules/graphql", body, {"Content-Type":"application/json","Authorization":AUTH,"Origin":HOST})
    return json.load(urllib.request.urlopen(req))

def ensure_folder(rel):
    path = f"/sites/{SITE}/files/{rel}"
    r = gql(f'{{jcr(workspace:EDIT){{nodeByPath(path:"{path}"){{uuid}}}}}}')
    if (r.get("data",{}).get("jcr") or {}).get("nodeByPath"): return
    parent, _, name = rel.rpartition("/")
    ppath = f"/sites/{SITE}/files/{parent}" if parent else f"/sites/{SITE}/files"
    gql(f'mutation{{jcr{{mutateNode(pathOrId:"{ppath}"){{addChild(name:"{name}",primaryNodeType:"jnt:folder"){{uuid}}}}}}}}')
    gql(f'mutation{{jcr{{mutateNode(pathOrId:"{path}"){{publish}}}}}}')

# basename -> original https source, from the source manifest (for migrated images)
man = json.load(open(f"orchestration/images/{PROJECT}.json"))
BASE = man["base"]
basemap = {}
for entries in man["pages"].values():
    for e in entries:
        basemap[e["file"]] = e["src"] if e["src"].startswith("http") else BASE + e["src"]

import_cache = {}
def ensure_dam(https, folder, fname):
    if https in import_cache: return import_cache[https]
    path = f"/sites/{SITE}/files/{folder}/{fname}"
    up = {}
    for _ in range(3):
        up = mcp("media.upload.url", {"siteKey": SITE, "sourceUrl": https, "folder": folder, "fileName": fname})
        if up.get("identifier") or (up.get("error") or {}).get("code") == "conflict": break
    uuid = up.get("identifier")
    if not uuid and (up.get("error") or {}).get("code") == "conflict":
        r = gql(f'{{jcr(workspace:EDIT){{nodeByPath(path:"{path}"){{uuid}}}}}}')
        nb = (r.get("data",{}).get("jcr",{}) or {}).get("nodeByPath")
        uuid = nb.get("uuid") if nb else None
    if not uuid:
        print(f"      upload failed: {str(up)[:140]}"); return None
    gql(f'mutation{{jcr{{mutateNode(pathOrId:"{path}"){{publish}}}}}}')
    import_cache[https] = uuid
    return uuid

def sanitize(name):
    keep = "".join(c.lower() if c.isalnum() or c in "-_." else "-" for c in name)
    return keep.strip("-") or "image.jpg"

def node_uuid(jcrpath, ws):
    r = gql(f'{{jcr(workspace:{ws}){{nodeByPath(path:"{jcrpath}"){{uuid}}}}}}')
    nb = (r.get("data",{}).get("jcr") or {}).get("nodeByPath")
    return nb.get("uuid") if nb else None

# (nodeType, url-string field, weakreference field). Convention: <name>ExternalUrl -> <name>.
TYPE_PAIRS = [
    (f"{NS}:editorialBlock","imageExternalUrl","image"),
    (f"{NS}:imgContentBlock","imageExternalUrl","image"),
    (f"{NS}:pagesPushesItem","imageExternalUrl","image"),
    (f"{NS}:trendCard","imageExternalUrl","image"),
    (f"{NS}:partnerLogo","logoExternalUrl","logo"),
    (f"{NS}:partnerEntry","logoExternalUrl","logo"),
]
ensure_folder(DAMFOLDER)
ok = fail = 0
for nodeType, urlField, wref in TYPE_PAIRS:
    q = (f'{{jcr(workspace:EDIT){{nodesByQuery(query:"SELECT * FROM [{nodeType}] WHERE '
         f'{urlField} IS NOT NULL AND ISDESCENDANTNODE(\'/sites/{SITE}/home\')")'
         f'{{nodes{{path u:property(name:"{urlField}"){{value}}}}}}}}}}')
    try:
        nodes = gql(q)["data"]["jcr"]["nodesByQuery"]["nodes"]
    except Exception as e:
        print(f"query {nodeType} failed: {e}"); continue
    print(f"{nodeType}.{urlField} -> {wref}: {len(nodes)} candidates")
    for n in nodes:
        path = n["path"]; url = (n.get("u") or {}).get("value","")
        label = path.split("/home/")[-1]
        uuid = None
        if f"/sites/{SITE}/files/" in url:                       # image already in Jahia DAM
            jcr = "/sites/" + url.split("/sites/",1)[1]
            eu, lu = node_uuid(jcr, "EDIT"), node_uuid(jcr, "LIVE")
            if eu and eu == lu:                                  # existing node, consistent UUID -> reference directly
                uuid = eu
            else:                                                # mismatched (servlet) -> re-import from CDN source
                rel = url.split(f"/sites/{SITE}/files/",1)[1]
                folder, basen = rel.rsplit("/",1); stem,_,ext = basen.rpartition(".")
                https = basemap.get(basen)
                if https: uuid = ensure_dam(https, folder, f"{stem}-dam.{ext}")
        elif url.startswith("http"):                              # external CDN hot-link -> import
            fname = sanitize(url.rsplit("/",1)[-1]); fname = fname if "." in fname else fname+".jpg"
            uuid = ensure_dam(url, DAMFOLDER, fname)
        try:
            if not uuid:
                print(f"  SKIP/FAIL {label}: no usable source ({url.rsplit('/',1)[-1]})"); fail += 1; continue
            gql(f'mutation{{jcr{{mutateNode(pathOrId:"{path}"){{mutateProperty(name:"{wref}"){{setValue(type:WEAKREFERENCE,value:"{uuid}")}}}}}}}}')
            gql(f'mutation{{jcr{{mutateNode(pathOrId:"{path}"){{mutateProperty(name:"{urlField}"){{delete}}}}}}}}')  # clear url string
            gql(f'mutation{{jcr{{mutateNode(pathOrId:"{path}"){{publish}}}}}}')
            ok += 1
            if ok % 10 == 0: print(f"    ...{ok} done")
        except Exception as e:
            print(f"  FAIL {label}: {e}"); fail += 1
print(f"\n{ok} images -> weakref (+url cleared), {fail} failed")
