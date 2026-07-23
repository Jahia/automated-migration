#!/usr/bin/env python3
"""model-contract.py — BLOCKING gate for the content-model contract (2026-07-16).

The contract (operator decision after the SingPost model review):
  - mixins are compose-into-types, AT-MOST-ONCE property blocks. Repetition is
    NEVER mixins: no numbered contrib families (contribBody2, contribLabel3…).
  - no bodyN fields anywhere: a node owns at most ONE body richtext; anything
    beyond is a CHILD node type (+ * (ns:cta), + * (ns:cardItem)).
  - the structural set ALWAYS ships: ns:jcrQuery, ns:gridRow, one
    jmix:mainResource type, ns:cta as a reusable child type.
  - SDC: every component folder with views carries its own definition.cnd.

--phase cnd     checks the MODULE (CND files + folders)     usage: <module_dir> <ns>
--phase content checks the LOADED JCR (no bodyN props; containers carry their
                children's content)                          usage: <site>
Exit 0 clean / 1 violations (each printed with file:line or node path).
"""
import glob
import json
import os
import re
import sys


def fail_list(title, items):
    if items:
        print(f"FAIL[{title}]:")
        for i in items:
            print(f"  - {i}")
    return len(items)


def phase_cnd(module, ns):
    bad = 0
    cnds = glob.glob(f"{module}/settings/*.cnd") + glob.glob(f"{module}/src/components/**/definition.cnd", recursive=True)
    text = {}
    for p in cnds:
        text[p] = open(p, encoding="utf-8").read()
    allcnd = "\n".join(text.values())

    # 1. numbered contrib mixin families. CONTRACT AMENDMENT (2026-07-20):
    # numbered contribBody/contribLabel mixins are PERMITTED — they carry
    # POSITIONED runs (a fragment living in a different wrapper than the body
    # slot, e.g. the home hero's Track-panel header inside its grid card),
    # added per node by the loader (the jmix:externalLink pattern; no editor-
    # form bloat). REPETITION stays forbidden as slots — enforced where it is
    # observable: reconcile-check's image-hoard + decompose gates force
    # repeated items into child node types. Numbered Image/Link mixins remain
    # forbidden (media units and links have child/weakref homes).
    fams = {}
    for p, t in text.items():
        for m in re.finditer(r"\[\w+:(contrib(?:Image|Link))(\d+)\]", t):
            fams.setdefault(m.group(1), []).append(f"{p}: {m.group(0)}")
    bad += fail_list("numbered-contrib-mixins (media/link repetition must be "
                     "child node types)",
                     [x for v in fams.values() for x in v])

    # 2. bodyN declared ON TYPES (mixins excepted per the amendment above):
    # a type-level bodyN sizes EVERY node's editor form to the richest
    # instance — the original violation; per-node mixins do not.
    body_n = []
    for p, t in text.items():
        blocks = re.split(r"(?=^\[)", t, flags=re.M)
        for b in blocks:
            head = b.split("\n", 1)[0]
            if re.search(r"\[\w+:contribBody\d+\]", head):
                continue
            for m in re.finditer(r"^\s*-\s*body\d+\s*\(", b, re.M):
                body_n.append(f"{p}: {m.group(0).strip()} (in {head.strip()[:40]})")
    bad += fail_list("bodyN-fields on TYPES (one body; positioned runs ride "
                     "per-node contribBodyN mixins)", body_n)

    # 3. structural set
    for need, why in ((f"[{ns}:jcrQuery]", "listing dimension (queryContent)"),
                      (f"[{ns}:gridRow]", "layout dimension"),
                      (f"[{ns}:cta]", "reusable CTA child type"),
                      ("jmix:mainResource", "entity/detail-page dimension")):
        if need not in allcnd:
            bad += fail_list("structural-set", [f"missing {need} — {why}"])

    # 4. SDC: every component folder with views has its own definition.cnd.
    # The STRUCTURAL/SHARED set (one definition each, in settings) is exempt:
    # their views live in folders but the single type definition is shared.
    shared_defined = set(re.findall(r"\[\w+:(\w+)\]", "\n".join(
        t for p, t in text.items() if "/settings/" in p)))
    missing_sdc = []
    for d in sorted(glob.glob(f"{module}/src/components/*/")):
        views = glob.glob(f"{d}*.server.tsx")
        folder = os.path.basename(d.rstrip("/"))
        tname = folder[0].lower() + folder[1:]
        if views and not os.path.isfile(f"{d}definition.cnd") \
                and tname not in shared_defined:
            missing_sdc.append(d)
    bad += fail_list("sdc (definition.cnd per component folder)", missing_sdc)
    return bad


def phase_content(site):
    import base64
    import urllib.request
    BASE = os.environ.get("JAHIA_URL", "http://localhost:8080")

    def gql(q):
        req = urllib.request.Request(f"{BASE}/modules/graphql",
                                     json.dumps({"query": q}).encode(),
                                     {"Content-Type": "application/json", "Origin": BASE})
        req.add_header("Authorization", "Basic " + base64.b64encode(
            f"{os.environ.get('JAHIA_USER', 'root')}:{os.environ.get('JAHIA_PASS', 'root')}".encode()).decode())
        return json.loads(urllib.request.urlopen(req, timeout=60).read())

    bad = 0
    # 1. no node carries a bodyN property — EXCEPT through the contribBodyN
    # slot mixins (2026-07-23, same exception the type-level rule already
    # grants): a positioned run whose marker lives in a DIFFERENT wrapper
    # than body's rides its own sanctioned slot (structure-aware merge,
    # 2026-07-20 hero fix) — folding it would rip it out of its grid cell.
    # Flattened repetition = body2 WITHOUT the slot mixin.
    d = gql('{jcr(workspace:EDIT){nodesByQuery(query:"SELECT * FROM [nt:base] AS n '
            f"WHERE ISDESCENDANTNODE(n,'/sites/{site}') AND n.[body2] IS NOT NULL\","
            'queryLanguage:SQL2,limit:20){nodes{path mixinTypes{name}}}}}')
    hits = [n["path"] for n in d["data"]["jcr"]["nodesByQuery"]["nodes"]
            if not any("contribBody" in (m.get("name") or "")
                       for m in (n.get("mixinTypes") or []))]
    bad += fail_list("jcr-bodyN (flattened repetition loaded onto parents)", hits)

    # 2. containers carry their content ON CHILDREN: a jnt:contentList-ish parent
    # with 0 children but a big own body is the collapse signature
    d = gql('{jcr(workspace:EDIT){nodesByQuery(query:"SELECT * FROM [jnt:content] AS n '
            f"WHERE ISDESCENDANTNODE(n,'/sites/{site}')\",queryLanguage:SQL2,limit:500)"
            '{nodes{path primaryNodeType{name} children{nodes{name}} '
            'body:property(name:\"body\",language:\"en\"){value}}}}}')
    collapsed = []
    for n in d["data"]["jcr"]["nodesByQuery"]["nodes"]:
        nt = n["primaryNodeType"]["name"]
        kids = len((n.get("children") or {}).get("nodes") or [])
        body = ((n.get("body") or {}).get("value")) or ""
        if ("Grid" in nt or "grid" in nt or "List" in nt) and kids == 0 and len(body) > 1500:
            collapsed.append(f"{n['path']} ({nt}: 0 children, body {len(body)} chars)")
    bad += fail_list("container-collapse (content in parent, children empty/absent)", collapsed)

    # 3. DISPLAY-NOT-EDITABLE (2026-07-16 finding): an item whose hidden
    # skeleton carries visible text while BOTH jcr:title and body are empty
    # renders content the Content Editor cannot touch — dead authoring.
    dead = []
    d = gql('{jcr(workspace:EDIT){nodesByQuery(query:"SELECT * FROM [jnt:content] AS n '
            f"WHERE ISDESCENDANTNODE(n,'/sites/{site}')\","
            'queryLanguage:SQL2,limit:1000){nodes{path type:primaryNodeType{name} '
            'sk:property(name:"skeleton"){value} '
            't:property(name:"jcr:title",language:"en"){value} '
            'b:property(name:"body",language:"en"){value} '
            'b2:property(name:"body2",language:"en"){value}}}}}')
    nodes = ((d.get("data") or {}).get("jcr") or {}).get("nodesByQuery", {}).get("nodes") or []
    if not nodes:
        # a gate that cannot MEASURE must fail loudly, never pass silently
        # (2026-07-16: a query syntax error returned [] and the gate passed
        # while nodes held 1.8KB of unauthorable text)
        bad += fail_list("gate-blind", [f"content query returned 0 nodes for site {site} "
                                        f"(errors: {str(d.get('errors'))[:200]})"])
        return bad
    hoarding = []
    for n in nodes:
        sk = ((n.get("sk") or {}).get("value")) or ""
        t = ((n.get("t") or {}).get("value")) or ""
        b = ((n.get("b") or {}).get("value")) or ""
        if not sk:
            continue
        # RESIDUAL text = what the skeleton still holds after every marker is
        # accounted for: markers reference properties/children (fine); any
        # other visible text is content an editor cannot author (CONTRACT v2:
        # skeleton is STRUCTURE ONLY). Applies to EVERY node, not just items.
        residual = re.sub(r"\{\{[^}]+\}\}", " ", sk)
        residual = re.sub(r"<[^>]+>", " ", residual)
        residual = re.sub(r"\s+", " ", residual).strip()
        b2 = ((n.get("b2") or {}).get("value")) or ""
        # a positioned body2 SLOT is an editable field (contrib mixin — same
        # amendment as rule 1, 2026-07-23); only title+body+slots all empty
        # counts as dead authoring
        if n["type"]["name"].endswith(":cardItem") and len(residual) >= 24 \
                and not t.strip() and not b.strip() and not b2.strip():
            dead.append(f"{n['path']} (skeleton text {len(residual)} chars, no editable field)")
        if len(residual) >= 60:
            hoarding.append(f"{n['path']} [{n['type']['name']}] holds "
                            f"{len(residual)} chars of unauthorable text")
    bad += fail_list("display-not-editable (item text has no editable field)", dead[:15])
    bad += fail_list("skeleton-holds-content (structure only — text belongs in properties)",
                     hoarding[:15])
    return bad


def main():
    if "--phase" not in sys.argv:
        sys.exit("usage: model-contract.py --phase cnd <module_dir> <ns> | --phase content <site>")
    phase = sys.argv[sys.argv.index("--phase") + 1]
    args = [a for a in sys.argv[1:] if a not in ("--phase", phase)]
    bad = phase_cnd(args[0], args[1]) if phase == "cnd" else phase_content(args[0])
    if bad:
        print(f"FAIL: model-contract ({phase}) — {bad} violation group(s)", file=sys.stderr)
        sys.exit(1)
    print(f"PASS: model-contract ({phase})")


if __name__ == "__main__":
    main()
