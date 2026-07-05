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
    # restrict image pickers to image nodes, matching the reference modules
    # (`- image (weakreference, picker[type='image']) < jmix:image`).
    if f["name"] == "image" and "weakreference" in typ:
        line += " < jmix:image"
    return line


def has_link_field(fields):
    return any(f["name"] == "j:linkType" or "linkType" in f.get("type", "") for f in fields)


def base_mixins(mixns):
    """Module-level base mixins emitted once. Matches the deployed reference modules
    (supercar-garage / lesalondelaphoto / sial-paris settings/definitions.cnd)."""
    return [
        f"[{mixns}:component] > jmix:droppableContent, jmix:accessControllableContent mixin",
        f"[{mixns}:pageComponent] > {mixns}:component mixin",
    ]


def link_lines():
    # A contributor link: j:linkType choicelist + a label, DIRECTLY on the type — no
    # linkTo mixin. j:url / j:linknode are injected at runtime by Jahia's built-in
    # mixins (jmix:externalLink / jmix:internalLink) and must NEVER be declared in the
    # CND. Verified against all three deployed reference modules (an explicit comment
    # in supercar-garage/settings/definitions.cnd states exactly this).
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


def _supertypes(fields, mixns, main_resource=False):
    """Supertype list for a block. Only mix:title is hoisted (it provides jcr:title);
    links + images stay inline on the type, matching the deployed reference modules."""
    st = ["jnt:content", f"{mixns}:component"]
    if any(f["name"] == "title" for f in fields):
        st.insert(1, "mix:title")                    # provides jcr:title — never declare title
    if main_resource:
        st.append("jmix:mainResource")
    return st


def _own_fields(fields):
    """Fields emitted inline on the type. title is covered by mix:title; j:linkType +
    linkLabel are emitted by link_lines() to keep the canonical order/keywords."""
    out = []
    for f in fields:
        if f["name"] == "title":
            continue
        if f["name"] == "j:linkType" or "linkType" in f.get("type", ""):
            continue
        if f["name"] == "linkLabel":
            continue
        out.append(f)
    return out


def _body_lines(n_runs):
    """body..bodyN richtext props — one per lifted text run (P2.5)."""
    out = []
    for n in range(n_runs):
        name = "body" if n == 0 else f"body{n + 1}"
        out.append(f"  - {name} (string, richtext) i18n")
    return out


def _media_lines(n_units):
    """image..imageN weakrefs + hidden companions (P2.5-C2): imageNOrig holds
    the unit's exact source markup (byte-exact default render), imageNOrigRef
    the UUID of the DAM copy of the original file — the view renders the
    original verbatim while the weakref still points at it, and the chosen
    image once an editor changes it."""
    out = []
    for i in range(n_units):
        nm = "image" if i == 0 else f"image{i + 1}"
        out.append(f"  - {nm} (weakreference, picker[type='image']) < jmix:image")
        out.append(f"  - {nm}Orig (string, textarea) hidden")
        out.append(f"  - {nm}OrigRef (string) hidden")
    return out


def contrib_mixins(mixns, stats):
    """P2.5-C fix (observed live): declaring body..bodyN / imageN / link props
    on the TYPE sizes every node's editor form to the RICHEST instance of that
    type — nodes without those runs show unjustified EMPTY fields. Jahia's
    per-node answer is MIXINS (the jmix:externalLink pattern): each slot is a
    module-level mixin the loader adds ONLY on nodes that actually carry the
    field. Sized to the global max across the content-load."""
    if not stats:
        return []
    max_runs = max([0] + [max(e.get("runs", 0), e.get("childRuns", 0))
                          for e in stats.values()])
    max_media = max([0] + [max(e.get("media", 0), e.get("childMedia", 0))
                           for e in stats.values()])
    any_link = any(e.get("link") or e.get("childLink") for e in stats.values())
    out = ["// P2.5-C contribution slots — added PER NODE by the loader, so the",
           "// editor form shows exactly the fields the node really carries"]
    for n in range(max_runs):
        nm = "contribBody" if n == 0 else f"contribBody{n + 1}"
        out.append(f"[{mixns}:{nm}] mixin")
        out.extend(_body_lines(n + 1)[n:])  # just the n-th body line
        out.append("")
    for i in range(max_media):
        nm = "contribImage" if i == 0 else f"contribImage{i + 1}"
        out.append(f"[{mixns}:{nm}] mixin")
        out.extend(_media_lines(i + 1)[3 * i:])  # just the i-th unit's 3 lines
        out.append("")
    if any_link:
        out.append(f"[{mixns}:contribLink] mixin")
        out.extend(link_lines())
        out.append("  - linkOrig (string) hidden")
        out.append("")
    return out


def type_block(comp, ns, mixns, stats=None):
    """Emit the CND [ns:type] block for a component (and return child block text).

    stats (P2.5, from --content-load): per-nodeType observed lift shape
    {runs, childRuns, titles, childTitles}. When present for a SKELETON type,
    the type declares ONLY wired properties — title (mix:title) + body..bodyN
    richtext + hidden skeleton. Shape-derived image/link/text props are dropped
    until the phase that wires them: a declared-but-unwired prop is a DEAD prop
    (shown in Content Editor, edits change nothing) — G1 requires zero."""
    node = comp["nodeType"]
    fields = comp.get("fields", []) or []
    st = (stats or {}).get(node)
    wired_only = bool(comp.get("skeleton")) and st is not None
    # wired-only types declare NO editable props at type level: title/body*/
    # image*/link live in the acqmix:contrib* slot mixins (+ mix:title), added
    # PER NODE by the loader — a node's editor form shows exactly what it
    # carries (observed live: type-level body..bodyN meant empty unjustified
    # fields on every leaner node of the type)
    supertypes = _supertypes([] if wired_only else fields,
                             mixns, comp.get("needsMainResource"))

    lines = [f"[{node}] > {', '.join(supertypes)}"]
    if not wired_only:
        for f in _own_fields(fields):
            lines.append(field_line(f))
        if has_link_field(fields):
            lines.extend(link_lines())
    if comp.get("skeleton"):
        # P2 skeleton rendering: the instance's own markup with {{f:name}}
        # markers — the view substitutes property values (pixel-exact +
        # editable fields). Hidden: contributors edit the FIELDS, not the markup.
        lines.append("  - skeleton (string, textarea) hidden")
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
            if wired_only:
                # items are skeleton nodes too — same per-node mixin contract
                csuper = _supertypes([], mixns)
                clines = [f"[{child_node}] > {', '.join(csuper)}"]
                clines.append("  - skeleton (string, textarea) hidden")
            else:
                cfields = child.get("fields", []) or []
                csuper = _supertypes(cfields, mixns)
                clines = [f"[{child_node}] > {', '.join(csuper)}"]
                for f in _own_fields(cfields):
                    clines.append(field_line(f))
                if has_link_field(cfields):
                    clines.extend(link_lines())
            child_text = "\n".join(clines)
        else:
            # container WITHOUT a typed item: never reference an undefined
            # {node}Item type — the OSGi bundle then carries an unresolvable
            # nodetype requirement and the whole module fails to start
            # (observed live: scg:keyFiguresItem). Accept module components.
            lines.append(f"  + * ({mixns}:component)")
    return "\n".join(lines), child_text


def run_stats_from_content_load(path, manifest):
    """content-load -> per-nodeType observed lift shape (P2.5 CND sizing):
    {runs: max body-runs on the type, childRuns: max on its items,
     titles/childTitles: any instance lifted a title}. Types with no promoted
    instance stay absent (their block keeps the manifest shape)."""
    itm = {k.lower(): v for k, v in (manifest.get("instanceTypeMap") or {}).items()}
    data = json.load(open(path))
    st = {}
    for page in data.get("pages", {}).values():
        for inst in page.get("instances", []):
            # promoted skeleton instances AND lifted anonymous raw blocks
            if not (inst.get("promoted")
                    or (inst.get("passthrough") and inst.get("skeleton"))):
                continue
            nt = itm.get((inst.get("type") or "").lower())
            if not nt:
                continue
            e = st.setdefault(nt, {"runs": 0, "childRuns": 0,
                                   "titles": False, "childTitles": False,
                                   "media": 0, "childMedia": 0,
                                   "link": False, "childLink": False})
            e["runs"] = max(e["runs"], sum(1 for k in inst.get("fields", {})
                                           if k.startswith("body")))
            e["titles"] |= "title" in inst.get("fields", {})
            e["media"] = max(e["media"], len(inst.get("media") or []))
            e["link"] |= bool(inst.get("link"))
            for ch in inst.get("children") or []:
                e["childRuns"] = max(e["childRuns"],
                                     sum(1 for k in ch.get("fields", {})
                                         if k.startswith("body")))
                e["childTitles"] |= "title" in ch.get("fields", {})
                e["childMedia"] = max(e["childMedia"], len(ch.get("media") or []))
                e["childLink"] |= bool(ch.get("link"))
    return st


def query_and_grid_types(ns, mixns, raw_runs=0, raw_stats=None):
    """Every module ships a JCRQuery + GridRow (migration.md rule 12 / CLAUDE.md rule 16):
    the editor's primary tools for building listing/grid pages without a developer.
    JCRQuery is `jmix:list` ONLY — the deployed reference modules deliberately omit
    jmix:renderableList (it limits the type to built-in views and injects j:linknode/
    j:url, breaking the custom default.server.tsx view). GridRow holds any component.

    raw_runs (P2.5): demoted anonymous blocks lift their text runs too — rawHtml
    then also carries a hidden skeleton + body..bodyN richtext (same mechanism,
    honest name; no mix:title — headings stay inside the richtext runs).
    raw_stats (P2.5-C): media weakrefs + contributor link on lifted raw blocks."""
    rs = raw_stats or {}
    raw_lines = [
        "// passthrough (P1.2): verbatim source markup for regions no semantic",
        "// component covers — the nothing-is-dropped half of the fidelity invariant.",
        "// P2.5: lifted raw blocks carry contribution slots via acqmix:contrib*",
        "// mixins (added per node by the loader) + the hidden skeleton.",
        f"[{ns}:rawHtml] > jnt:content, {mixns}:component",
        "  - html (string, textarea)",
        # a {{child:N}} container IS a rawHtml node holding typed component
        # children (emit_container_live) — without a child-node definition the
        # content-editor form builder throws for every nested child
        # ("Error while building edit form definition", G6 red on 12 nodes).
        f"  + * ({mixns}:component)",
    ]
    if raw_runs or rs.get("runs") or rs.get("media") or rs.get("link"):
        raw_lines.append("  - skeleton (string, textarea) hidden")
    return [
        f"// listing + grid tools (editor-facing, every module ships these)",
        f"[{ns}:jcrQuery] > jnt:content, {mixns}:component, jmix:list",
        "  - query (string, textarea)",
        "  - maxItems (long) = 10",
        "  - subNodeView (string) = 'card'",
        "",
        f"[{ns}:gridRow] > jnt:content, {mixns}:component",
        "  - columns (long) = 3 < 1, 2, 3, 4, 6, 12",
        "  - gap (string, choicelist) = 'md' < 'none', 'sm', 'md', 'lg'",
        f"  + * ({mixns}:component)",
        "",
        *raw_lines,
        "",
    ]


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
    ap.add_argument("--content-load",
                    help="content-load.json — sizes body..bodyN per type from the "
                         "OBSERVED lift (P2.5 wired-only CND for skeleton types)")
    args = ap.parse_args()

    m = json.load(open(args.manifest))
    ns, mixns, proj = args.ns, args.mixns, args.project
    stats = None
    if args.content_load:
        stats = run_stats_from_content_load(args.content_load, m)
        print(f"[cnd_emit] wired-only sizing from {args.content_load}: "
              f"{len(stats)} promoted type(s)", file=sys.stderr)

    header = [
        "<jnt = 'http://www.jahia.org/jahia/nt/1.0'>",
        "<jmix = 'http://www.jahia.org/jahia/mix/1.0'>",
        "<mix = 'http://www.jcp.org/jcr/mix/1.0'>",
        f"<{ns} = 'https://jahia.com/{proj}/nt/1.0'>",
        f"<{mixns} = 'https://jahia.com/{proj}/mix/1.0'>",
        "",
        *base_mixins(mixns),
        "",
    ]
    body, children, view_plans = [], [], []
    body.extend(contrib_mixins(mixns, stats))
    raw_stats = (stats or {}).get(f"{ns}:rawHtml", {})
    body.extend(query_and_grid_types(ns, mixns, raw_stats=raw_stats))
    view_plans.append({"component": "JCR Query", "nodeType": f"{ns}:jcrQuery",
                       "views": ["default.server.tsx"]})
    view_plans.append({"component": "Grid Row", "nodeType": f"{ns}:gridRow",
                       "views": ["default.server.tsx"], "childType": f"{mixns}:component"})
    view_plans.append({"component": "Raw HTML (passthrough)", "nodeType": f"{ns}:rawHtml",
                       "views": ["default.server.tsx"],
                       "note": "renders the html property verbatim (server-side, no Island)"})

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
        blk, child = type_block(c, ns, mixns, stats=stats)
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
