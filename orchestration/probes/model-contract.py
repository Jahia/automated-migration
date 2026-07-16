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

    # 1. numbered contrib mixin families = faking repetition with mixins
    fams = {}
    for p, t in text.items():
        for m in re.finditer(r"\[\w+:(contrib(?:Body|Image|Label|Link))(\d+)\]", t):
            fams.setdefault(m.group(1), []).append(f"{p}: {m.group(0)}")
    bad += fail_list("numbered-contrib-mixins (repetition must be child node types)",
                     [x for v in fams.values() for x in v])

    # 2. bodyN fields anywhere
    body_n = [f"{p}: {m.group(0).strip()}" for p, t in text.items()
              for m in re.finditer(r"^\s*-\s*body\d+\s*\(", t, re.M)]
    bad += fail_list("bodyN-fields (merge into ONE body; beyond = children)", body_n)

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
    # 1. no node carries a bodyN property
    d = gql('{jcr(workspace:EDIT){nodesByQuery(query:"SELECT * FROM [nt:base] AS n '
            f"WHERE ISDESCENDANTNODE(n,'/sites/{site}') AND n.[body2] IS NOT NULL\","
            'queryLanguage:SQL2,limit:20){nodes{path}}}}')
    hits = [n["path"] for n in d["data"]["jcr"]["nodesByQuery"]["nodes"]]
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
