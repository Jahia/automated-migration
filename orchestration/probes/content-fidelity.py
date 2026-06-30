#!/usr/bin/env python3
"""content-fidelity.py — gate that the migrated CONTENT matches reality, not just
structure. Our other gates prove the site is built correctly (renders, deploys, CND
valid); a structurally-perfect but HOLLOW site (empty listings, no images, blank shell,
no EN, debris) passes them all. This checks the recurring 'far from reality' gaps:

  shell    — /home/nav and /home/footer have child content (AbsoluteArea-needs-children;
             blank in edit otherwise)
  images   — image-bearing content actually has its image weakref set (not text-only heroes)
  listings — jmix:mainResource detail content EXISTS (news/agenda listings aren't empty)
  en       — published content carries EN translations (AGENTS rule 4: en+fr minimum)
  cleanup  — no test/temp/orphan debris nodes left in the tree

Usage: content-fidelity.py <siteKey> <project_path> [langs-csv]
Exit 0 only if every check passes.
"""
import base64, json, os, sys, glob, urllib.request

HOST = os.environ.get("JAHIA_HOST", "http://localhost:8080").rstrip("/")
USER = os.environ.get("JAHIA_USER", "root:root")
if len(sys.argv) < 3:
    sys.exit("usage: content-fidelity.py <siteKey> <project_path> [langs-csv]")
SITE, PROJ = sys.argv[1], sys.argv[2]
LANGS = sys.argv[3].split(",") if len(sys.argv) > 3 else ["fr", "en"]
GQL = f"{HOST}/modules/graphql"
AUTH = "Basic " + base64.b64encode(USER.encode()).decode()
esc = lambda p: p.replace("'", "''")
SCOPE = f"isdescendantnode('/sites/{esc(SITE)}')"
fails, notes = [], []

def gql(q):
    req = urllib.request.Request(GQL, data=json.dumps({"query": q}).encode(),
        headers={"Content-Type": "application/json", "Origin": HOST, "Authorization": AUTH})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def nodes(sql, ws="EDIT", extra="path"):
    d = gql(f'{{jcr(workspace:{ws}){{nodesByQuery(query:"{esc(sql) if False else sql}"){{nodes{{uuid {extra}}}}}}}}}')
    if d.get("errors"):
        return None
    return d["data"]["jcr"]["nodesByQuery"]["nodes"]

# ── 1. shell-populated ────────────────────────────────────────────────────────
for region in ("nav", "footer"):
    d = gql(f'{{jcr(workspace:EDIT){{nodeByPath(path:"/sites/{SITE}/home/{region}")'
            f'{{children{{nodes{{name}}}}}}}}}}')
    np = (((d.get("data") or {}).get("jcr") or {}).get("nodeByPath"))
    if np is None:
        notes.append(f"shell: /home/{region} node not found (shared region not created yet)")
    else:
        n = len((np.get("children") or {}).get("nodes", []))
        if n == 0:
            fails.append(f"shell: /home/{region} has 0 child content nodes — blank in edit (AbsoluteArea-needs-children); populate it")

# ── 2. images-present ─────────────────────────────────────────────────────────
content = nodes(f"select * from [jnt:content] where {SCOPE}") or []
img_set = 0
img_props = ("image", "backgroundImage", "logo", "photo", "visual", "bannerImage", "thumbnailImage")
# requery with properties to inspect weakref image fields
d = gql(f'{{jcr(workspace:EDIT){{nodesByQuery(query:"select * from [jnt:content] where {SCOPE}")'
        f'{{nodes{{path properties{{name values definition{{requiredType}}}}}}}}}}}}')
allnodes = (((d.get("data") or {}).get("jcr") or {}).get("nodesByQuery") or {}).get("nodes", [])
for n in allnodes:
    for p in n.get("properties", []):
        if p["name"] in img_props and (p.get("definition") or {}).get("requiredType") == "WEAKREFERENCE":
            if p.get("values"):
                img_set += 1
if allnodes and img_set == 0:
    fails.append(f"images: not a single image weakref is set across {len(allnodes)} content nodes — the site is text-only (heroes/cards have no images). Wire DAM images.")
else:
    notes.append(f"images: {img_set} image weakref(s) set across {len(allnodes)} content nodes")

# ── 3. listings — mainResource detail content exists ──────────────────────────
mr = nodes(f"select * from [jmix:mainResource] where {SCOPE}") or []
# expected: cached article/detail pages under the section listings
exp = len(glob.glob(f"{PROJ}/.reference/cache/_crawl/**/actus/*.html", recursive=True)) \
    + len(glob.glob(f"{PROJ}/.reference/cache/_crawl/**/agenda-photo/*.html", recursive=True))
if len(mr) == 0:
    fails.append(f"listings: 0 jmix:mainResource nodes exist — news/agenda listings are EMPTY (reference has ~{exp} detail pages). Create the article/event content.")
elif exp and len(mr) < 0.5 * exp:
    fails.append(f"listings: only {len(mr)} mainResource nodes vs ~{exp} in the reference (<50%) — listings far below the source")
else:
    notes.append(f"listings: {len(mr)} mainResource nodes (reference ~{exp})")

# ── 4. en translations ────────────────────────────────────────────────────────
if "en" in LANGS:
    titled = nodes(f"select * from [mix:title] where {SCOPE}") or []
    sample = [n["uuid"] for n in titled][:60]
    fr_only = 0
    for i in range(0, len(sample), 30):
        chunk = sample[i:i + 30]
        body = " ".join(f'a{j}:nodeById(uuid:"{u}"){{en:property(name:"jcr:title",language:"en"){{value}} '
                         f'fr:property(name:"jcr:title",language:"fr"){{value}}}}' for j, u in enumerate(chunk))
        d = gql(f"{{jcr(workspace:EDIT){{{body}}}}}")
        jc = (d.get("data") or {}).get("jcr") or {}
        for k, v in jc.items():
            if v and (v.get("fr") and v["fr"].get("value")) and not (v.get("en") and v["en"].get("value")):
                fr_only += 1
    if sample and fr_only > 0.2 * len(sample):
        fails.append(f"en: {fr_only}/{len(sample)} sampled titled nodes have FR but no EN title (>20%) — EN under-populated (AGENTS rule 4: en+fr minimum)")
    elif fr_only:
        notes.append(f"en: {fr_only}/{len(sample)} sampled nodes missing EN title (under threshold)")

# ── 5. cleanup — no debris ────────────────────────────────────────────────────
debris = []
for n in (content or []):
    base = n["path"].rsplit("/", 1)[-1].lower()
    if base.startswith("test") or base in ("test2", "test-home") or "-old" in base or base.startswith("untitled"):
        debris.append(n["path"])
if debris:
    fails.append(f"cleanup: {len(debris)} test/temp/old debris node(s): {', '.join(debris[:6])}")

# ── report ────────────────────────────────────────────────────────────────────
for n in notes:
    print("  ·", n)
if fails:
    print("\nCONTENT-FIDELITY FAILURES:")
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print("\ncontent-fidelity: shell populated, images present, listings have content, EN present, no debris")
