#!/usr/bin/env python3
"""Repopulate a stub page with REAL reference content - MCP ONLY.
Reads orchestration/pages/<project>/<page-slug>.json and fills the page's
hero / intro / editorialBlock components, importing every image as a DAM
weakreference via media.upload.url (never a *Url string). Creates blocks that
don't exist yet; updates those that do. Publishes the page subtree (fr).

Manifest schema:
{ "base": "<cdn base url>", "page": "le-salon",
  "hero":  { "heading": "...", "subtitle": "...", "image": "<path rel to base>", "imgFile": "hero.jpg" },
  "intro": { "overline": "...", "heading": "...", "body": "<p>..</p>" },
  "blocks": [ { "heading": "...", "body": ["<p>..</p>","<h3>..</h3>"], "image": "<rel>", "imgFile": "b0.jpg",
               "imageAlt": "...", "ctaLabel": "...", "dark": false } ] }

Usage: python3 orchestration/pages/migrate_page.py <project> <page-slug> [siteKey] [ns] [locale]
"""
import sys, json, urllib.request
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "sial-paris"
PAGE = sys.argv[2]
SITE = sys.argv[3] if len(sys.argv) > 3 else PROJECT
NS = sys.argv[4] if len(sys.argv) > 4 else "sialp"
LOC = sys.argv[5] if len(sys.argv) > 5 else "fr"
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

man = json.load(open(f"orchestration/pages/{PROJECT}/{PAGE.replace('/', '__')}.json"))
base = man["base"]
main = f"/sites/{SITE}/home/{PAGE}/main"
img_cache = {}

def import_image(rel, fname):
    if not rel: return None
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

def upsert(name, ntype, props, removep):
    path = f"{main}/{name}"
    exists = mcp("content.get", {"path": path, "locale": LOC}).get("identifier")
    if exists:
        r = mcp("content.update", {"path": path, "locale": LOC, "properties": props, "removeProperties": removep})
        act = "upd"
    else:
        r = mcp("content.create", {"parentPath": main, "nodeType": ntype, "name": name, "locale": LOC, "properties": props})
        act = "new"
    print(f"  {act} {name}: {'ERR '+str(r['error'])[:80] if r.get('error') else 'ok'}")

if man.get("hero"):
    h = man["hero"]; img = import_image(h.get("image"), h.get("imgFile"))
    p = {k: h[k] for k in ("heading", "subtitle") if h.get(k)}
    if img: p["backgroundImage"] = img
    upsert("hero", f"{NS}:pageHero", p, ["backgroundImageUrl"])
if man.get("intro"):
    it = man["intro"]
    upsert("intro", f"{NS}:introText", {k: it[k] for k in ("overline", "heading", "body") if it.get(k)}, [])
for i, b in enumerate(man.get("blocks", [])):
    img = import_image(b.get("image"), b.get("imgFile"))
    p = {"heading": b.get("heading", ""), "body": "".join(b.get("body", []))}
    for k in ("imageAlt", "ctaLabel"):
        if b.get(k): p[k] = b[k]
    if b.get("dark"): p["darkBackground"] = "true"
    if img: p["image"] = img
    upsert(f"block-{i}", f"{NS}:editorialBlock", p, ["imageExternalUrl", "ctaUrl"])

pub = mcp("publication.publish", {"path": f"/sites/{SITE}/home/{PAGE}", "languages": [LOC], "includeSubTree": True})
print(f"publish {PAGE}: {'ERR' if pub.get('error') else 'ok'}")
