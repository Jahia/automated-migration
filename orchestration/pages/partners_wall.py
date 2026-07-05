#!/usr/bin/env python3
"""Build a partner logo wall on the nos-partenaires page - MCP ONLY.
Reads orchestration/pages/<project>/nos-partenaires-logos.txt (one CDN-relative logo
path per line; category is encoded in the folder name). For each: import the logo into
the DAM as a weakreference (media.upload.url), create a <ns>:partnerEntry under a
<ns>:partnersList on the page (title + partnerCategory derived from filename/folder),
then publish. Removes the stub editorialBlocks first. Idempotent on re-run.
Usage: python3 orchestration/pages/partners_wall.py [project] [page] [siteKey] [ns] [locale]
"""
import sys, re, json, os, urllib.request
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "sial-paris"
PAGE = sys.argv[2] if len(sys.argv) > 2 else "le-salon/nos-partenaires"
SITE = sys.argv[3] if len(sys.argv) > 3 else PROJECT
NS = sys.argv[4] if len(sys.argv) > 4 else "sialp"
LOC = sys.argv[5] if len(sys.argv) > 5 else "fr"
BASE = "https://www.sialparis.com/-/media/Project/Comexposium-Master1/Master1-sialparis/"
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

CAT = {"Logo-Instit": "institutionnels", "Logo-Animations": "animations",
       "Logo-Media": "medias", "Nouveaux-logos-medias": "medias",
       "Logo-Salon": "salons", "Logo-Insight": "sialInsights"}

def derive(path):
    folder = path.split("/")[-2] if "/" in path else ""
    cat = next((v for k, v in CAT.items() if k in path), "medias")
    fn = os.path.splitext(path.split("/")[-1])[0]
    n = re.sub(r"(?i)^logo[-_ ]*", "", fn)
    n = re.sub(r"(?i)[-_ ]*partenaire[-_ ]*de[-_ ]*sial[-_ ]*paris", "", n)
    n = re.sub(r"(?i)[-_ ]*partners?[-_ ]*list[-_ ]*sial.*$", "", n)
    n = re.sub(r"[-_]+", " ", n).strip()
    n = re.sub(r"\s+\d+$", "", n)  # drop trailing version numbers
    return (n.title() if n.islower() or n.isupper() else n) or fn, cat

main = f"/sites/{SITE}/home/{PAGE}/main"
listpath = f"{main}/partners"
paths = [l.strip() for l in open(f"orchestration/pages/{PROJECT}/nos-partenaires-logos.txt") if l.strip()]

# 1. remove stub editorial blocks (keep hero + intro)
for n in ("block-0", "block-1", "block-2", "block-3"):
    g = mcp("content.get", {"path": f"{main}/{n}", "locale": LOC})
    if g.get("identifier"):
        mcp("content.mark_for_deletion", {"path": f"{main}/{n}"})

# 2. ensure the partnersList exists
if not mcp("content.get", {"path": listpath, "locale": LOC}).get("identifier"):
    r = mcp("content.create", {"parentPath": main, "nodeType": f"{NS}:partnersList",
                               "name": "partners", "locale": LOC, "properties": {"heading": "Nos partenaires et sponsors"}})
    print("partnersList:", "ERR " + str(r.get("error"))[:80] if r.get("error") else "created")

ok = fail = 0
for i, rel in enumerate(paths):
    name, cat = derive(rel)
    fname = f"partner-{i:03d}-" + re.sub(r"[^a-zA-Z0-9.]+", "-", rel.split("/")[-1])
    up = mcp("media.upload.url", {"siteKey": SITE, "sourceUrl": BASE + rel,
                                  "folder": "migrated/imported-media", "fileName": fname})
    uuid = up.get("identifier")
    if not uuid and (up.get("error") or {}).get("code") == "conflict":
        uuid = mcp("content.get", {"path": f"/sites/{SITE}/files/migrated/imported-media/{fname}", "locale": LOC}).get("identifier")
    if not uuid:
        print(f"  IMG-FAIL {name}: {str(up.get('error'))[:60]}"); fail += 1; continue
    mcp("publication.publish", {"path": f"/sites/{SITE}/files/migrated/imported-media/{fname}", "languages": [LOC]})
    ename = f"entry-{i:03d}"
    props = {"title": name, "logo": uuid, "partnerCategory": cat}
    g = mcp("content.get", {"path": f"{listpath}/{ename}", "locale": LOC})
    if g.get("identifier"):
        r = mcp("content.update", {"path": f"{listpath}/{ename}", "locale": LOC, "properties": props, "removeProperties": ["logoExternalUrl"]})
    else:
        r = mcp("content.create", {"parentPath": listpath, "nodeType": f"{NS}:partnerEntry",
                                   "name": ename, "locale": LOC, "properties": props})
    if r.get("error"): print(f"  ENTRY-FAIL {name}: {str(r['error'])[:70]}"); fail += 1
    else: ok += 1
print(f"\n{ok} partner entries, {fail} failed. Publishing page...")
pub = mcp("publication.publish", {"path": f"/sites/{SITE}/home/{PAGE}", "languages": [LOC], "includeSubTree": True})
print("publish:", "ERR " + str(pub.get("error"))[:80] if pub.get("error") else "ok")
