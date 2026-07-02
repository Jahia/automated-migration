#!/usr/bin/env python3
"""cnd_emit.py — Deterministic CND + view-plan emitter (analyze phase → step 4/5).

Turns the assembled component manifest into:
  - a Jahia CND (settings/definitions.cnd content) — node types, mixins, fields,
    containers/child types, layout choicelists, mainResource supertypes;
  - a view plan (which *.server.tsx views each component needs).

Both are DETERMINISTIC functions of the manifest — no LLM. View identification
follows fixed rules from usage flags:
  - needsMainResource        -> default (card/teaser) + fullPage (detail page)
  - isContainer              -> default; its child type gets a card view
  - layoutProperty present   -> single default view that branches on the property
  - otherwise                -> default only

Mirrors the repo's real CND conventions (usgmix:component base mixin, mix:title
for titles, j:linkType for links, picker[type='image'] weakreferences).

Usage:
  python3 orchestration/lib/cnd_emit.py <manifest.json> --ns usg --mixns usgmix \
      --project supercar-garage --out-cnd <definitions.cnd> --out-views <views.json>
"""
import argparse
import json
import re
import sys


def camel(s):
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", s or "") if p]
    return (parts[0].lower() + "".join(p.capitalize() for p in parts[1:])) if parts else "x"


def local(nodetype):
    return nodetype.split(":", 1)[-1]


def field_line(f):
    """Emit one CND property line. Order: (type, selector) = default keywords < constraints."""
    name = f["name"]
    typ = f.get("type", "string")
    line = f"  - {name} ({typ})"
    if f.get("mandatory"):
        line += " mandatory"
    if f.get("i18n"):
        line += " i18n"
    return line


def link_lines():
    # A contributor link: j:linkType choicelist + a label. j:url / j:linknode are
    # injected at runtime by Jahia's built-in link mixins — never declared here.
    return [
        "  - j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no",
        "  - linkLabel (string) i18n",
    ]


def layout_line(lp):
    name = camel(lp.get("name", "layout"))
    opts = [o for o in (lp.get("options") or []) if o]
    if not opts:
        return None
    quoted = ", ".join(f"'{o}'" for o in opts)
    return f"  - {name} (string, choicelist) = '{opts[0]}' < {quoted}"


def type_block(comp, ns, mixns):
    """Emit the CND [ns:type] block for a component (and return child block text)."""
    node = comp["nodeType"]
    fields = comp.get("fields", []) or []
    has_title = any(f["name"] == "title" for f in fields)
    has_link = any("linkType" in (f.get("type", "")) or f["name"] == "j:linkType" for f in fields)

    supertypes = ["jnt:content", f"{mixns}:component"]
    if has_title:
        supertypes.insert(1, "mix:title")            # provides jcr:title — never declare title
    if comp.get("needsMainResource"):
        supertypes.append("jmix:mainResource")

    lines = [f"[{node}] > {', '.join(supertypes)}"]
    for f in fields:
        if f["name"] == "title" and has_title:
            continue                                  # covered by mix:title
        if f["name"] == "j:linkType" or "linkType" in f.get("type", ""):
            continue                                  # emitted via link_lines below
        lines.append(field_line(f))
    if has_link:
        lines.extend(link_lines())
    lp = comp.get("layoutProperty")
    if isinstance(lp, dict):
        ll = layout_line(lp)
        if ll:
            lines.append(ll)

    child_text = ""
    if comp.get("isContainer"):
        child = comp.get("childType")
        if isinstance(child, dict) and child.get("nodeType"):
            child_node = child["nodeType"]
            lines.append(f"  + * ({child_node})")
            cfields = child.get("fields", []) or []
            c_title = any(f["name"] == "title" for f in cfields)
            c_link = any("linkType" in f.get("type", "") or f["name"] == "j:linkType" for f in cfields)
            csuper = ["jnt:content", f"{mixns}:component"]
            if c_title:
                csuper.insert(1, "mix:title")
            clines = [f"[{child_node}] > {', '.join(csuper)}"]
            for f in cfields:
                if f["name"] == "title" and c_title:
                    continue
                if f["name"] == "j:linkType" or "linkType" in f.get("type", ""):
                    continue
                clines.append(field_line(f))
            if c_link:
                clines.extend(link_lines())
            child_text = "\n".join(clines)
        else:
            lines.append(f"  + * ({node}Item)")
    return "\n".join(lines), child_text


def views_for(comp):
    """Deterministic view plan for a component."""
    node = comp["nodeType"]
    views = ["default.server.tsx"]
    if comp.get("needsMainResource"):
        views.append("fullPage.server.tsx")
    plan = {"component": comp["name"], "nodeType": node, "views": views}
    if comp.get("layoutProperty"):
        plan["defaultViewBranchesOn"] = comp["layoutProperty"].get("name")
    if comp.get("isContainer") and isinstance(comp.get("childType"), dict):
        plan["childType"] = comp["childType"]["nodeType"]
        plan["childViews"] = ["default.server.tsx", "card.server.tsx"]
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--ns", default="ns")
    ap.add_argument("--mixns", default="nsmix")
    ap.add_argument("--project", default="site")
    ap.add_argument("--out-cnd")
    ap.add_argument("--out-views")
    args = ap.parse_args()

    m = json.load(open(args.manifest))
    ns, mixns, proj = args.ns, args.mixns, args.project

    header = [
        "<jnt = 'http://www.jahia.org/jahia/nt/1.0'>",
        "<jmix = 'http://www.jahia.org/jahia/mix/1.0'>",
        "<mix = 'http://www.jcp.org/jcr/mix/1.0'>",
        f"<{ns} = 'https://jahia.com/{proj}/nt/1.0'>",
        f"<{mixns} = 'https://jahia.com/{proj}/mix/1.0'>",
        "",
        f"[{mixns}:component] > jmix:droppableContent, jmix:accessControllableContent mixin",
        f"[{mixns}:pageComponent] > {mixns}:component mixin",
        "",
    ]
    body, children, view_plans = [], [], []

    for c in m.get("crossCutting", []) or []:
        # cross-cutting components are page-area (absolute) content types too
        cc = dict(c)
        cc.setdefault("fields", c.get("fields", []))
        blk, child = type_block(cc, ns, mixns)
        body.append("// cross-cutting (AbsoluteArea: %s)" % c.get("area", "?"))
        body.append(blk + "\n")
        if child:
            children.append(child + "\n")
        view_plans.append(views_for(cc))

    for c in m.get("components", []) or []:
        blk, child = type_block(c, ns, mixns)
        tags = []
        if c.get("isContainer"):
            tags.append("container")
        if c.get("needsMainResource"):
            tags.append("mainResource")
        if c.get("layoutProperty"):
            tags.append("layout:" + c["layoutProperty"].get("name", ""))
        body.append(f"// {c['name']}  covers={c.get('coversRoles')}  {tags}")
        body.append(blk + "\n")
        if child:
            children.append(child + "\n")
        view_plans.append(views_for(c))

    cnd = "\n".join(header) + "\n".join(body) + "\n// ── child types ──\n" + "\n".join(children)

    if args.out_cnd:
        open(args.out_cnd, "w").write(cnd)
    else:
        print(cnd)
    if args.out_views:
        json.dump({"project": proj, "namespace": ns, "views": view_plans},
                  open(args.out_views, "w"), indent=2, ensure_ascii=False)

    n_types = len(m.get("components", []) or []) + len(m.get("crossCutting", []) or [])
    n_child = len(children)
    n_views = sum(len(v["views"]) + len(v.get("childViews", [])) for v in view_plans)
    print(f"[cnd_emit] {n_types} types + {n_child} child types -> {args.out_cnd or '(stdout)'}; "
          f"{n_views} views planned -> {args.out_views or '(none)'}", file=sys.stderr)


if __name__ == "__main__":
    main()
