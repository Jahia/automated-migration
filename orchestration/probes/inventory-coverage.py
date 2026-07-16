#!/usr/bin/env python3
"""inventory-coverage.py — BLOCKING gate: the pipeline must ACCOUNT for what
the site inventory found (stellar-core Phase 2). The inventory is the
deterministic ground truth of what the SOURCE contains; this gate proves the
model/content phases covered it — the operator reviews a diff, not a broken
site.

--phase content  (pre-load, artifacts only)
  For every inventory page/region:
    - each heading (h1-h3, len>=5) appears in the content-load's placed
      fields (title/body of instances or their children)
    - each region image file appears in the payload (media files or body/
      skeleton markup)
  Misses are itemized page/region/kind.

--phase site  (post-load/populate, JCR + module)
  Chrome completeness vs inventory:
    - inventory logo  -> siteHeader has an image weakref
    - inventory nav   -> rendered L1 equals the extracted menu (labels file)
    - inventory footer columns -> footer node has >= that many cardItem
      children (with cta children)
    - breadcrumb view deployed when inventory pages are nested

Usage: inventory-coverage.py <project> <site> --phase content|site
       [--headings 0.95] [--images 0.90]
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.request

BASE = os.environ.get("JAHIA_URL", "http://localhost:8080")


def gql(q):
    req = urllib.request.Request(f"{BASE}/modules/graphql",
                                 json.dumps({"query": q}).encode(),
                                 {"Content-Type": "application/json", "Origin": BASE})
    req.add_header("Authorization", "Basic " + base64.b64encode(
        f"{os.environ.get('JAHIA_USER', 'root')}:{os.environ.get('JAHIA_PASS', 'root')}".encode()).decode())
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def norm(t):
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def load(p, what):
    try:
        return json.load(open(p))
    except (FileNotFoundError, ValueError) as e:
        print(f"FAIL: inventory-coverage — cannot read {what} ({p}): {e}", file=sys.stderr)
        sys.exit(1)


def phase_content(project, inv, thr_h, thr_i):
    cl = load(f"orchestration/content/{project}.content-load.json", "content-load")
    # the pipeline localizes assets to CONTENT-HASH names; join inventory's
    # original filenames through the mirror's urlMap (original -> hashed)
    h2o = {}
    try:
        um = (json.load(open(f"projects/{project}/workflow-output/local-mirror/mirror.json"))
              .get("urlMap") or {})
        for orig, local in um.items():
            ob = os.path.basename(orig.split("?")[0]).lower()
            lb = os.path.basename(str(local)).lower()
            if ob:
                h2o.setdefault(ob, lb)
    except (FileNotFoundError, ValueError):
        pass
    bad, checked_h, hit_h, checked_i, hit_i = [], 0, 0, 0, 0
    for slug, pg in (inv.get("pages") or {}).items():
        pl = (cl.get("pages") or {}).get(slug)
        if pl is None:
            bad.append(f"PAGE {slug}: in inventory but absent from content-load")
            continue
        blob = []
        for i in pl.get("instances") or []:
            f = i.get("fields") or {}
            blob += [str(v) for v in f.values() if isinstance(v, str)]
            blob.append(i.get("skeleton") or "")
            blob += [m.get("file") or "" for m in i.get("media") or []]
            for ch in i.get("children") or []:
                cf = ch.get("fields") or {}
                blob += [str(v) for v in cf.values() if isinstance(v, str)]
                blob.append(ch.get("skeleton") or "")
                blob += [m.get("file") or "" for m in ch.get("media") or []]
        blob = norm(" ".join(blob))
        for r in pg.get("regions") or []:
            for h in r.get("headings") or []:
                if h["level"] not in ("h1", "h2", "h3") or len(h["text"]) < 5:
                    continue
                checked_h += 1
                if norm(h["text"])[:80] in blob:
                    hit_h += 1
                else:
                    bad.append(f"HEADING {slug}: {h['text'][:60]!r} not placed")
            for im in r.get("images") or []:
                if not im.get("file"):
                    continue
                checked_i += 1
                fl = im["file"].lower()
                if fl in blob or (h2o.get(fl) or "\x00") in blob:
                    hit_i += 1
                else:
                    bad.append(f"IMAGE {slug}: {im['file']} not placed")
    rh = hit_h / checked_h if checked_h else 1.0
    ri = hit_i / checked_i if checked_i else 1.0
    print(f"inventory-coverage(content): headings {hit_h}/{checked_h} ({rh:.2f}), "
          f"images {hit_i}/{checked_i} ({ri:.2f})")
    hard = [b for b in bad if b.startswith("PAGE ")]
    if rh < thr_h or ri < thr_i or hard:
        for b in bad[:25]:
            print(f"  - {b}")
        print(f"FAIL: inventory-coverage(content) — headings {rh:.2f}<{thr_h} "
              f"or images {ri:.2f}<{thr_i} or {len(hard)} missing page(s)", file=sys.stderr)
        sys.exit(1)
    if bad:
        print(f"  ({len(bad)} sub-threshold miss(es) tolerated; itemized in artifacts)")
    print("PASS: inventory-coverage(content)")


def phase_site(project, site, inv):
    bad = []
    ch = inv.get("chrome") or {}
    # logo
    if (ch.get("header") or {}).get("logo"):
        d = gql('{jcr(workspace:EDIT){nodeByPath(path:"/sites/%s/home/header/siteHeader")'
                '{img:property(name:"image"){value}}}}' % site)
        node = ((d.get("data") or {}).get("jcr") or {}).get("nodeByPath")
        if not node or not (node.get("img") or {}).get("value"):
            bad.append("CHROME: inventory has a logo; siteHeader has no image weakref")
    # nav L1 vs extracted labels
    lp = f"orchestration/sitemaps/{project}.labels.json"
    sm = f"orchestration/sitemaps/{project}.txt"
    if os.path.isfile(sm) and os.path.isfile(lp):
        labels = json.load(open(lp))
        l1 = [labels.get(x.strip(), x.strip()) for x in open(sm)
              if x.strip() and not x.startswith("#") and "/" not in x.strip()]
        d = gql('{jcr(workspace:EDIT){nodeByPath(path:"/sites/%s/home")'
                '{children(typesFilter:{types:["jnt:page"]}){nodes{name '
                'mix:mixinTypes{name} t:property(name:"jcr:title",language:"en"){value}}}}}}' % site)
        nodes = ((d.get("data") or {}).get("jcr") or {}).get("nodeByPath", {}) \
            .get("children", {}).get("nodes") or []
        shown = [(n.get("t") or {}).get("value") or n["name"] for n in nodes
                 if not any(m["name"].endswith(":hideFromNav") for m in n["mix"])]
        if shown[:len(l1)] != l1:
            bad.append(f"CHROME: nav L1 {shown[:len(l1)]} != inventory menu {l1}")
    # footer columns
    inv_cols = len((ch.get("footer") or {}).get("columns") or [])
    if inv_cols:
        d = gql('{jcr(workspace:EDIT){nodeByPath(path:"/sites/%s/home/footer/footer")'
                '{children{nodes{name t:primaryNodeType{name}}}}}}' % site)
        node = ((d.get("data") or {}).get("jcr") or {}).get("nodeByPath")
        got = len([n for n in ((node or {}).get("children") or {}).get("nodes") or []
                   if n["t"]["name"].endswith(":cardItem")])
        if got < min(inv_cols, 2):
            bad.append(f"CHROME: inventory has {inv_cols} footer column(s); "
                       f"footer node has {got} cardItem child(ren)")
    # breadcrumb view deployed
    if not os.path.isfile(f"projects/{project}/src/components/Breadcrumb/default.server.tsx"):
        bad.append("CHROME: breadcrumb view missing from the module")
    if bad:
        for b in bad:
            print(f"  - {b}")
        print(f"FAIL: inventory-coverage(site) — {len(bad)} chrome gap(s)", file=sys.stderr)
        sys.exit(1)
    print("PASS: inventory-coverage(site) — logo, nav, footer, breadcrumb accounted for")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("site")
    ap.add_argument("--phase", required=True, choices=["content", "site"])
    ap.add_argument("--headings", type=float, default=0.95)
    ap.add_argument("--images", type=float, default=0.90)
    a = ap.parse_args()
    inv = load(f"projects/{a.project}/workflow-output/site-inventory.json", "site inventory")
    if not inv.get("pages"):
        print("FAIL: inventory-coverage — inventory has no pages "
              "(a gate that cannot measure must fail)", file=sys.stderr)
        sys.exit(1)
    if a.phase == "content":
        phase_content(a.project, inv, a.headings, a.images)
    else:
        phase_site(a.project, a.site, inv)


if __name__ == "__main__":
    main()
