#!/usr/bin/env python3
"""Generic jmix:mainResource article migrator - MCP ONLY (news, focus, any card listing).
Reads a manifest { base, folder, articles:[{name, title, excerpt?, date?, image?, imgFile?, body?[]}] }
and creates/updates <nodeType> nodes under /sites/<site>/<folder>, importing each image as a DAM
weakreference (media.upload.url) and publishing (fr). Title goes to jcr:title (mix:title).
Usage: python3 orchestration/articles/migrate_articles.py <project> <manifest_path> <nodeType> [siteKey] [ns] [locale]
  e.g. ... orchestration/focus/sial-paris.json sialp:focusArticle sial-paris sialp fr
"""
import sys, json, urllib.request
PROJECT = sys.argv[1]
MANIFEST = sys.argv[2]
NODETYPE = sys.argv[3]
SITE = sys.argv[4] if len(sys.argv) > 4 else PROJECT
NS = sys.argv[5] if len(sys.argv) > 5 else "sialp"
LOC = sys.argv[6] if len(sys.argv) > 6 else "fr"
tok = ""; host = "http://localhost:8080"
for line in open(f"projects/{PROJECT}/.env"):
    line = line.strip()
    if line.startswith("JAHIA_HOST="): host = line.split("=", 1)[1]
    elif line.startswith("JAHIA_MCP_TOKEN="): tok = line.split("=", 1)[1]

def mcp(name, args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}}).encode()
    req = urllib.request.Request(host + "/modules/mcp", body,
        {"Content-Type": "application/json", "Authorization": "APIToken " + tok})
    txt = json.load(urllib.request.urlopen(req)).get("result", {}).get("content", [{}])[0].get("text", "")
    try: return json.loads(txt)
    except Exception: return {"_raw": txt}

man = json.load(open(MANIFEST))
base = man["base"]; folder = man.get("folder")
folder_path = f"/sites/{SITE}/{folder}"
cache = {}

def import_image(rel, fname):
    if not rel: return None
    if rel in cache: return cache[rel]
    up = mcp("media.upload.url", {"siteKey": SITE, "sourceUrl": rel if rel.startswith("http") else base + rel,
                                  "folder": "migrated/imported-media", "fileName": fname})
    uuid = up.get("identifier")
    if not uuid and (up.get("error") or {}).get("code") == "conflict":
        uuid = mcp("content.get", {"path": f"/sites/{SITE}/files/migrated/imported-media/{fname}", "locale": LOC}).get("identifier")
    if uuid:
        mcp("publication.publish", {"path": f"/sites/{SITE}/files/migrated/imported-media/{fname}", "languages": [LOC]})
        cache[rel] = uuid
    return uuid

ok = fail = 0
for a in man["articles"]:
    if not a.get("title"): continue
    name = a["name"]; path = f"{folder_path}/{name}"
    props = {"jcr:title": a["title"]}
    if a.get("excerpt"): props["excerpt"] = a["excerpt"]
    if a.get("body"): props["body"] = "".join(a["body"])
    if a.get("date"): props["publishDate"] = a["date"] + "T00:00:00.000"
    img = import_image(a.get("image"), a.get("imgFile")) if a.get("image") else None
    if img: props["thumbnail"] = img
    exists = mcp("content.get", {"path": path, "locale": LOC}).get("identifier")
    if exists:
        r = mcp("content.update", {"path": path, "locale": LOC, "properties": props, "removeProperties": ["title"]})
    else:
        r = mcp("content.create", {"parentPath": folder_path, "nodeType": NODETYPE,
                                   "name": name, "locale": LOC, "properties": props})
    if r.get("error"):
        print(f"  FAIL {name}: {str(r['error'])[:90]}"); fail += 1; continue
    pub = mcp("publication.publish", {"path": path, "languages": [LOC], "includeSubTree": True})
    print(f"  {'OK' if not pub.get('error') else 'PUB-ERR'} {name}  (img {'y' if img else 'n'})")
    ok += 1
print(f"\n{ok} {NODETYPE} migrated (MCP), {fail} failed")
