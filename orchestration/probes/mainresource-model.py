#!/usr/bin/env python3
"""mainresource-model.py — jmix:mainResource entities must be COMPOSED, not flattened.

Structured content is the whole point of modelling an entity as `jmix:mainResource`
instead of a page: an editor opens an article and edits its parts. Two core defects
defeated that, and both were invisible to every other gate:

  1. **CND**: mainResource types carried `+ * (ns:cardItem)` / `(ns:cta)` /
     `(ns:subNavigation)` but never `+ * (nsmix:component)`, so a band child
     (richTextSection, mediaText, …) failed `ConstraintViolationException: No child
     node definition found` — CLAUDE.md rule 17. They also lacked `jmix:list`, so
     Jahia's list rendering and cache invalidation never applied.
  2. **LOADER**: `load_main_resources` therefore had no choice but
     `body = "".join(main.children)` — the entire article as ONE richtext property.
     Measured on Salon de la Photo: a 7-band article and an 11-band exhibition page
     (4 inline images) collapsed into a single field, freezing every image and the
     video block out of the editor's reach.

Phases:
  --phase cnd  <project_path> <ns>   every mainResource type in the CND extends
                                     jmix:list and accepts nsmix:component children
  --phase content <site> [--locale]  every mainResource node in the live EDIT tree
                                     has band children, and NO node's own body
                                     carries structural markup that belongs in a
                                     band (<img>, <iframe>, 2+ headings) — the
                                     flattening signature, measured on the artifact

Usage: mainresource-model.py --phase cnd <project_path> <ns>
       mainresource-model.py --phase content <site> [--locale fr]
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

FLAT_SIGNS = (
    ("<img", "an image that belongs in a media band as a DAM weakref"),
    ("<iframe", "an embed that belongs in its own band"),
)


def gql(query):
    r = subprocess.run(
        ["bash", "-c",
         'set -a; . .env.local 2>/dev/null; set +a; '
         'curl -s -u "$JAHIA_USER:$JAHIA_PASS" -H "Origin: $JAHIA_URL" '
         '-H "Content-Type: application/json" -X POST "$JAHIA_URL/modules/graphql" '
         f"-d '{json.dumps({'query': query})}'"],
        capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        sys.exit(f"FAIL mainresource-model: GraphQL unreadable ({r.stdout[:120]})")


def phase_cnd(pp, ns):
    cnds = ([f"{pp}/settings/definitions.cnd"]
            + sorted(glob.glob(f"{pp}/src/**/definition.cnd", recursive=True))
            + sorted(glob.glob(f"{pp}/workflow-output/definitions.cnd")))
    text = ""
    for c in cnds:
        if os.path.exists(c):
            text += open(c, encoding="utf-8", errors="replace").read() + "\n"
    if not text.strip():
        sys.exit(f"FAIL mainresource-model[cnd]: no CND found under {pp}")
    mixns = f"{ns}mix"
    blocks = re.split(r"(?m)^\[", text)
    fails, checked = [], []
    for b in blocks:
        if "jmix:mainResource" not in b.split("\n")[0]:
            continue
        name = b.split("]")[0].strip()
        checked.append(name)
        head = b.split("\n")[0]
        if "jmix:list" not in head:
            fails.append(f"{name}: not a container — `jmix:list` missing from its "
                         f"supertypes, so Jahia's list rendering + cache never apply")
        if f"+ * ({mixns}:component)" not in b:
            fails.append(f"{name}: no `+ * ({mixns}:component)` child rule — every "
                         f"band child will fail ConstraintViolationException, forcing "
                         f"the loader to flatten the body into one richtext")
    if not checked:
        sys.exit("FAIL mainresource-model[cnd]: no jmix:mainResource type in the CND — "
                 "an entity map without an entity type migrates news as pages")
    if fails:
        print(f"FAIL mainresource-model[cnd] — {len(checked)} mainResource type(s)")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print(f"PASS mainresource-model[cnd]: {', '.join(checked)} — each a jmix:list "
          f"container accepting {mixns}:component band children")


def phase_content(site, locale):
    q = ('{jcr(workspace:EDIT){nodesByQuery(query:"select * from [jmix:mainResource] '
         'where isdescendantnode([/sites/%s])"){nodes{path primaryNodeType{name} '
         'children{nodes{name primaryNodeType{name}}} '
         'property(name:\\"body\\" language:\\"%s\\"){value}}}}}' % (site, locale))
    d = gql(q)
    nodes = (((d.get("data") or {}).get("jcr") or {})
             .get("nodesByQuery") or {}).get("nodes")
    if nodes is None:
        sys.exit(f"FAIL mainresource-model[content]: query failed "
                 f"({json.dumps(d)[:200]})")
    if not nodes:
        sys.exit(f"FAIL mainresource-model[content]: 0 jmix:mainResource nodes under "
                 f"/sites/{site} — entities were never loaded (or were loaded as pages)")
    flat, childless = [], []
    for n in nodes:
        body = ((n.get("property") or {}).get("value") or "")
        kids = [k for k in ((n.get("children") or {}).get("nodes") or [])]
        signs = [why for tok, why in FLAT_SIGNS if tok in body.lower()]
        if len(re.findall(r"<h[23]\b", body, re.I)) >= 2:
            signs.append("2+ section headings — a multi-band body in one property")
        if signs:
            flat.append((n["path"], signs))
        elif not kids and len(re.sub(r"<[^>]+>", "", body)) > 1200:
            childless.append((n["path"], len(body)))
    fails = []
    if flat:
        fails.append(f"{len(flat)} entity/entities carry a FLATTENED body: " +
                     "; ".join(f"{p.split('/')[-1]} ({', '.join(s)})"
                               for p, s in flat[:5]))
    if childless:
        fails.append(f"{len(childless)} entity/entities have a long body and NO band "
                     f"children: " + ", ".join(f"{p.split('/')[-1]} ({n}ch)"
                                               for p, n in childless[:5]))
    if fails:
        print(f"FAIL mainresource-model[content] — {len(nodes)} entity node(s) under "
              f"/sites/{site}")
        for f in fails:
            print(f"  - {f}")
        print("  Fix: load_main_resources decomposes the body into band children "
              "(entity_bands); a flat body means it fell back or the CND rejected "
              "the children.")
        sys.exit(1)
    withkids = sum(1 for n in nodes if ((n.get("children") or {}).get("nodes") or []))
    print(f"PASS mainresource-model[content]: {len(nodes)} entity node(s), "
          f"{withkids} with band children, no flattened body")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["cnd", "content"], required=True)
    ap.add_argument("args", nargs="*")
    ap.add_argument("--locale", default="en")
    a = ap.parse_args()
    if a.phase == "cnd":
        if len(a.args) < 2:
            sys.exit("usage: mainresource-model.py --phase cnd <project_path> <ns>")
        phase_cnd(a.args[0].rstrip("/"), a.args[1])
    else:
        if not a.args:
            sys.exit("usage: mainresource-model.py --phase content <site> [--locale]")
        phase_content(a.args[0], a.locale)


if __name__ == "__main__":
    main()
