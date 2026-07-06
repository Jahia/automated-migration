#!/usr/bin/env python3
"""editor-surface.py — G6: the EDITOR-SURFACE gate (CONTRIBUTION-PLAN §9).

The lesson behind this probe (observed live, three review rounds): JCR state
and pixel fidelity can both be green while the migration is still uneditable
IN PRACTICE. The editor surface has two halves, both deterministic:

  A. FORM — for every wired payload node, Content Editor's own form API
     (forms.editForm) must expose each wired prop as a read-write field in an
     activated fieldSet (title -> jcr:title, body*, imageN, link -> j:linkType).
  B. REACHABILITY — every item child node must have an EDIT FRAME ([path]
     module marker) in the Page Builder render: a correct form nobody can
     click through to is not editable in any real sense.

Usage: editor-surface.py <project> <site> [--lang en] [--pages N]
Exit 0 = PASS, 1 = FAIL.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from load_content import Loader  # noqa: E402


def wired_field_names(payload):
    """Wired props -> the field names Content Editor must expose read-write."""
    f = payload.get("fields") or {}
    out = []
    if f.get("title"):
        out.append("jcr:title")
    out.extend(k for k in f if k.startswith("body"))
    out.extend(m["name"] for m in (payload.get("media") or []) if m.get("file"))
    if payload.get("link"):
        out.append("j:linkType")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("site")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--pages", type=int, default=4)
    a = ap.parse_args()

    ld = Loader(a.project, a.site)
    pages = sorted(ld.content.get("pages", {}).keys())
    sample = pages[::4][:a.pages] or pages[:a.pages]
    failures = []

    # ── A. forms.editForm completeness on wired nodes (parents + items) ──
    checked_forms = 0
    for slug in sample:
        pdata = ld.content["pages"][slug]
        page_base = ld._slug_to_jcr_path(slug)
        created_path = {}
        for idx, inst in enumerate(pdata.get("instances", [])):
            if inst.get("area") or not inst.get("skeleton"):
                continue
            nt = ld.type_map.get((inst.get("type") or "").lower())
            if not nt:
                continue
            # parent nesting (matching the loader's parent_for logic): if the
            # instance references a parent that was already created, nest under
            # it; otherwise flat under the page's main area
            pi = inst.get("parent")
            if pi is not None and isinstance(pi, int) and pi in created_path:
                parent = created_path[pi]
            else:
                parent = f"{page_base}/main"
            node = f"{parent}/{nt.split(':')[-1]}-{slug}-{idx}"
            created_path[idx] = node  # track for children
            targets = [(node, inst)] + [(f"{node}/item-{n + 1}", ch)
                                        for n, ch in enumerate(inst.get("children") or [])]
            for npath, pl in targets[:6]:
                expect = wired_field_names(pl)
                if not expect:
                    continue
                q = ('{ forms { editForm(uiLocale: "en", locale: "%s", uuidOrPath: "%s") '
                     '{ sections { fieldSets { activated fields { name readOnly } } } } } }'
                     % (a.lang, npath))
                try:
                    r = ld.m.gql(q)
                except Exception as e:
                    failures.append((npath, f"editForm query failed: {str(e)[:120]}"))
                    continue
                rw = set()
                for s in r["forms"]["editForm"]["sections"]:
                    for fs in s["fieldSets"]:
                        if not fs["activated"]:
                            continue
                        for fld in fs["fields"]:
                            if not fld["readOnly"]:
                                rw.add(fld["name"])
                missing = [x for x in expect if x not in rw]
                checked_forms += 1
                if missing:
                    failures.append((npath, f"form lacks rw field(s): {missing}"))

    # ── B. Page Builder reachability of item nodes ──
    # creds via mcp_client (parses .env.local itself — `source` does NOT export,
    # so os.environ is empty in python children; observed live: blank login ->
    # about:blank editframe -> every item read as missing)
    host = ld.m.host
    user, _, pw = ld.m.user.partition(":")
    here = os.path.dirname(os.path.abspath(__file__))
    checked_items = 0
    for slug in sample:
        pdata = ld.content["pages"][slug]
        page_base = ld._slug_to_jcr_path(slug)
        created_path = {}
        expected = []
        for idx, inst in enumerate(pdata.get("instances", [])):
            if inst.get("area"):
                continue
            nt = ld.type_map.get((inst.get("type") or "").lower())
            if not nt:
                continue
            pi = inst.get("parent")
            # register EVERY instance path (same rule as the loader's
            # parent_for) — a childless wrapper container is still the JCR
            # parent of nested instances; skipping it predicted flat paths
            # for their item children (false "no edit frame", observed live
            # on the navify header nested under the page wrapper).
            if pi is not None and isinstance(pi, int) and pi in created_path:
                parent = created_path[pi]
            else:
                parent = f"{page_base}/main"
            node = f"{parent}/{nt.split(':')[-1]}-{slug}-{idx}"
            created_path[idx] = node
            if inst.get("children"):
                expected += [f"{node}/item-{n + 1}"
                             for n in range(len(inst["children"]))]
        if not expected:
            continue
        page_path = page_base.split("/home", 1)[-1].strip("/") or "home"
        if page_path != "home":
            page_path = "home/" + page_path
        try:
            out = subprocess.run(
                ["node", f"{here}/editor-surface.mjs", host, user, pw,
                 a.site, a.lang, page_path],
                capture_output=True, text=True, timeout=180)
            data = json.loads(out.stdout.strip() or "{}")
        except Exception as e:
            failures.append((slug, f"page-builder scan failed: {str(e)[:120]}"))
            continue
        if data.get("error"):
            # frame-not-loaded is ITS OWN failure — never misread as missing items
            failures.append((slug, f"editframe did not load: {data['error']}"))
            continue
        found = set(data.get("modulePaths") or [])
        for ip in expected:
            checked_items += 1
            if ip not in found:
                failures.append((ip, "item has NO edit frame in Page Builder "
                                     "(unreachable through the editorial flow)"))

    print(f"editor-surface: {checked_forms} form(s) checked, "
          f"{checked_items} item frame(s) checked")
    for f in failures[:12]:
        print(f"  ✗ {f[0]}\n      {f[1]}")
    print(("PASS" if not failures else "FAIL") + ": G6 editor-surface gate")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
