#!/usr/bin/env python3
"""Repeatable news migration - MCP ONLY (mandatory-first rule; GraphQL is never used here).

Reads a manifest orchestration/news/<project>.json:
  { "base": "<cdn base url>", "folder": "contents/news", "articles": [
      { "name": "<node-name>", "title": "...", "excerpt": "...", "date": "YYYY-MM-DD",
        "image": "<path relative to base>", "imgFile": "<dam filename>",
        "category": "<category node name or null>", "body": ["<p>..</p>","<h2>..</h2>", ...] } ] }

Per article (all via MCP tools):
  media.upload.url  -> import the real image (consistent UUID) into migrated/imported-media
  content.create / content.update (locale fr, properties incl thumbnail weakref + i18n title/excerpt/body)
  publication.publish (languages:[fr], includeSubTree) -> publishes the j:translation_fr subnode too

Usage: python3 orchestration/news/migrate_news.py [project] [siteKey] [ns] [locale]
"""
import json, sys, base64, urllib.request
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "sial-paris"
SITE = sys.argv[2] if len(sys.argv) > 2 else PROJECT
NS = sys.argv[3] if len(sys.argv) > 3 else "sialp"
LOC = sys.argv[4] if len(sys.argv) > 4 else "fr"

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

man = json.load(open(f"orchestration/news/{PROJECT}.json"))
base = man["base"]; folder = man.get("folder", "contents/news")
folder_path = f"/sites/{SITE}/{folder}"
img_cache = {}

def import_image(rel, fname):
    if rel in img_cache: return img_cache[rel]
    src = rel if rel.startswith("http") else base + rel
    up = mcp("media.upload.url", {"siteKey": SITE, "sourceUrl": src,
                                  "folder": "migrated/imported-media", "fileName": fname})
    uuid = up.get("identifier")
    if not uuid and (up.get("error") or {}).get("code") == "conflict":
        g = mcp("content.get", {"path": f"/sites/{SITE}/files/migrated/imported-media/{fname}", "locale": LOC})
        uuid = g.get("identifier")
    if uuid:
        mcp("publication.publish", {"path": f"/sites/{SITE}/files/migrated/imported-media/{fname}", "languages": [LOC]})
        img_cache[rel] = uuid
    return uuid

ok = fail = skip = 0
for a in man["articles"]:
    if a.get("done") or not a.get("title"):
        skip += 1; continue
    name = a["name"]; path = f"{folder_path}/{name}"
    # jcr:title is inherited from mix:title (i18n) - never a custom 'title' property
    props = {"jcr:title": a["title"], "excerpt": a.get("excerpt", ""), "body": "".join(a.get("body", []))}
    rm = ["title"]  # drop the legacy custom title property left on pre-migration nodes
    if a.get("date"): props["publishDate"] = a["date"] + "T00:00:00.000"
    img_uuid = import_image(a["image"], a["imgFile"]) if a.get("image") else None
    if img_uuid: props["thumbnail"] = img_uuid
    # create if missing, else update - both with locale for i18n props
    exists = mcp("content.get", {"path": path, "locale": LOC}).get("identifier")
    if exists:
        r = mcp("content.update", {"path": path, "locale": LOC, "properties": props, "removeProperties": rm})
    else:
        r = mcp("content.create", {"parentPath": folder_path, "nodeType": f"{NS}:newsArticle",
                                   "name": name, "locale": LOC, "properties": props})
    if (r.get("error")):
        print(f"  FAIL {name}: {str(r['error'])[:120]}"); fail += 1; continue
    pub = mcp("publication.publish", {"path": path, "languages": [LOC], "includeSubTree": True})
    status = "OK" if not pub.get("error") else f"PUB-ERR {str(pub.get('error'))[:80]}"
    print(f"  {status} {name}  (img {'y' if img_uuid else 'n'})")
    ok += 1 if status == "OK" else 0
print(f"\n{ok} articles migrated (MCP), {fail} failed, {skip} skipped (done/uncaptured)")
