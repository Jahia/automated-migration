#!/usr/bin/env python3
"""cta-link-check.py — BLOCKING gate: no cta node dead-ends.

Class caught 2026-07-20: the loader's editor-visible-props guard silently
dropped `linkOrig` (hidden by contract) for every lifted cta — payload carried
the href, the node lost it, every skeleton button rendered href="". Payload
gates (reconcile-check) cannot see this: the seam is payload -> JCR. This gate
reads the LIVE EDIT STATE.

Rule: every {ns}:cta node under the site that presents something clickable
(a linkLabel or a skeleton) must carry a link target — one of linkOrig, j:url,
or j:linknode. Exit 1 with named paths otherwise.

Usage: cta-link-check.py <site> <ns> [--locale en]
"""
import json
import os
import sys
import urllib.request


def gql(host, user, pw, query):
    req = urllib.request.Request(
        f"{host}/modules/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "Origin": host,
                 "Authorization": "Basic " + __import__("base64").b64encode(
                     f"{user}:{pw}".encode()).decode()})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def main():
    site, ns = sys.argv[1], sys.argv[2]
    locale = sys.argv[sys.argv.index("--locale") + 1] if "--locale" in sys.argv else "en"
    host = (os.environ.get("JAHIA_URL") or "http://localhost:8080").rstrip("/")
    user = (os.environ.get("JAHIA_USER") or "root").split(":")[0]
    pw = os.environ.get("JAHIA_PASS") or "root"
    q = ('query{jcr(workspace:EDIT){nodeByPath(path:"/sites/%s"){'
         'descendants(typesFilter:{types:["%s:cta"]}){nodes{path '
         'lbl:property(name:"linkLabel",language:"%s"){value} '
         'lo:property(name:"linkOrig"){value} '
         'ju:property(name:"j:url"){value} '
         'jn:property(name:"j:linknode"){value} '
         'sk:property(name:"skeleton"){value}}}}}}' % (site, ns, locale))
    d = gql(host, user, pw, q)
    nodes = (((d.get("data") or {}).get("jcr") or {}).get("nodeByPath") or {}) \
        .get("descendants", {}).get("nodes") or []
    dead = []
    for n in nodes:
        val = lambda k: ((n.get(k) or {}).get("value") or "").strip()  # noqa: E731
        clickable = val("lbl") or val("sk")
        target = val("lo") or val("ju") or val("jn")
        if clickable and not target:
            dead.append(f"{n['path']}  (label={val('lbl')[:40]!r})")
    if dead:
        print(f"FAIL: cta-link-check — {len(dead)}/{len(nodes)} cta node(s) "
              f"present a button with NO link target (dead-end):")
        for p in dead[:30]:
            print(f"  - {p}")
        sys.exit(1)
    print(f"PASS: cta-link-check — {len(nodes)} cta node(s), every clickable one "
          f"carries linkOrig / j:url / j:linknode")


if __name__ == "__main__":
    main()
