#!/usr/bin/env python3
"""cnd_emit.py — Deterministic CND + view-plan emitter (analyze phase → step 4/5).

Turns the assembled component manifest into:
  - a Jahia CND (settings/definitions.cnd content) — node types, mixins, fields,
    containers/child types, layout choicelists, mainResource supertypes;
  - a view plan (which *.server.tsx views each component needs).

Both are DETERMINISTIC functions of the manifest — no LLM. View identification
follows fixed rules from usage flags:
  - needsMainResource        -> default + card (what a jcrQuery lists) + fullPage
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
import os
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
        f"  - skeletonOrig (string, textarea) hidden",
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
    """The per-instance LAYOUT choicelist — AGENTS 2b's preferred lever: one type,
    a property the contributor flips in Content Editor, no new view and no new type.

    KEY MISMATCH (2026-08-03): this read `options` while every archetype in
    archetypes.py declares `values`, so it returned None and NOT ONE layout
    choicelist was ever emitted — mediaText's imageLeft/imageRight, cardGrid's
    grid/carousel/slider, layoutSection's stack/row and article/directoryEntry kinds
    were all silently absent from the CND, and the views' layout branches had no
    property to branch on. Accept both keys, and honour an explicit `default`."""
    name = camel(lp.get("name", "layout"))
    opts = [o for o in (lp.get("values") or lp.get("options") or []) if o]
    if not opts:
        return None
    first = lp.get("default") if lp.get("default") in opts else opts[0]
    quoted = ", ".join(f"'{o}'" for o in opts)
    return f"  - {name} (string, choicelist) = '{first}' < {quoted}"


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
    max_labels = max([0] + [max(e.get("labels", 0), e.get("childLabels", 0))
                            for e in stats.values()])
    for i in range(max_labels):
        nm = "contribLabel" if i == 0 else f"contribLabel{i + 1}"
        fld = "label" if i == 0 else f"label{i + 1}"
        out.append(f"[{mixns}:{nm}] mixin")
        out.append(f"  - {fld} (string) i18n")
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

    def _slot_max(fields, prefix):
        """Highest slot INDEX for body/label keys — slot numbering can be
        SPARSE (merges/pops leave gaps), so sizing by key COUNT under-declares
        the mixin ladder and the loader requests a contribLabelN the CND never
        emitted (observed live: NoSuchNodeTypeException contribLabel10)."""
        mx = 0
        for k in fields or {}:
            m = re.match(rf"{prefix}(\d*)$", k)
            if m:
                mx = max(mx, int(m.group(1) or 1))
        return mx

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
            e["runs"] = max(e["runs"], _slot_max(inst.get("fields"), "body"))
            e["labels"] = max(e.get("labels", 0), _slot_max(inst.get("fields"), "label"))
            e["titles"] |= "title" in inst.get("fields", {})
            e["media"] = max(e["media"], len(inst.get("media") or []))
            e["link"] |= bool(inst.get("link"))
            for ch in inst.get("children") or []:
                e["childRuns"] = max(e["childRuns"],
                                     _slot_max(ch.get("fields"), "body"))
                e["childLabels"] = max(e.get("childLabels", 0),
                                       _slot_max(ch.get("fields"), "label"))
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
        "// tree-driven main navigation (AIStartupKit rule 19: nav = page tree,",
        "// 3 levels, never frozen markup; view renders the source's own classes)",
        f"[{ns}:mainNavigation] > jnt:content, {mixns}:pageComponent",
        "",
        f"// listing + grid tools (editor-facing, every module ships these)",
        f"[{ns}:jcrQuery] > jnt:content, mix:title, {mixns}:pageComponent, jmix:list, jmix:cache",
        "  - maxItems (long) indexed=no",
        # CANONICAL DEFINITION — .agents/skills/06-implement-jcr-query/SKILL.md, which
        # says in as many words: "Do NOT ship a minimalist hardcoded-nodeType/basePath
        # variant — use this full component with criteria, sortDirection, filter,
        # loadMore, categoryFilter, j:subNodesView". This emitter shipped exactly the
        # minimalist variant (query textarea + plain-string type/sortBy/subNodeView), so
        # editors got free-text where the skill specifies pickers, and the properties the
        # views read (criteria/sortDirection/j:subNodesView) did not exist at all.
        #
        # `type` is driven by the marker mixin: subnodetypes auto-populates with every
        # type that opted in by extending {mixns}:queryContent (+ jnt:page), so the
        # dropdown stays short and curated instead of listing the whole catalogue. NO
        # space after the comma in the CSV — a space there is one of the five known
        # install-blocking CND faults.
        f"  - type (string, choicelist[subnodetypes='jnt:page,{mixns}:queryContent',"
        f"resourceBundle]) mandatory indexed=no",
        "  - criteria (string, choicelist[resourceBundle]) = 'jcr:created' autocreated "
        "indexed=no < 'jcr:created', 'jcr:lastModified', 'j:lastPublished'",
        "  - sortDirection (string, choicelist[resourceBundle]) = 'desc' autocreated "
        "indexed=no < 'asc', 'desc'",
        "  - startNode (weakreference) indexed=no",
        "  - excludeNodes (weakreference) multiple indexed=no",
        "  - filter (weakreference, category[autoSelectParent=false]) multiple indexed=no",
        "  - noResultText (string) i18n indexed=no",
        "  - j:subNodesView (string, choicelist[templates=subnodes,resourceBundle,image,"
        "dependentProperties='type']) nofulltext indexed=no",
        "  - j:linkType (string, choicelist[linkTypeInitializer]) indexed=no",
        "  - loadMore (boolean) = false indexed=no",
        "  - categoryFilter (boolean) = false indexed=no",
        # NO CHILD NODES ON A QUERY (operator, 2026-08-04). A jcrQuery RETRIEVES
        # jmix:mainResource nodes and renders each with subNodeView='card', linking
        # to the entity's fullPage view — the result set is the content, and it lives
        # in the entity folders, not under this node. Children were granted here on
        # 2026-07-23 because a STATIC card band occasionally got TYPED jcrQuery and
        # its decomposed children failed ConstraintViolation; that papered over a
        # typing bug with a permissive definition and left the model ambiguous — a
        # jcrQuery with children is neither a query nor a grid. A static card band
        # belongs to cardGrid, which is what holds cardItem children.
        "",
        # PER .agents/skills/04-define-content-types (2026-08-04). Three divergences
        # were invented here: `{mixns}:component` instead of pageComponent (so the grid
        # was not droppable in a page area), `columns (long)` instead of a
        # choicelist[resourceBundle] (no dropdown, no translated labels, and values 6/12
        # nobody asked for), and `+ * ({mixns}:component)` instead of
        # `+ * (jmix:droppableContent)` — which quietly forbade PLATFORM content in a
        # grid cell, so an editor could not drop a jnt:bigText into the layout tool whose
        # entire job is holding arbitrary content.
        f"[{ns}:gridRow] > jnt:content, {mixns}:pageComponent",
        "  - columns (string, choicelist[resourceBundle]) = '2' < '1', '2', '3', '4'",
        "  - gap (string, choicelist[resourceBundle]) = 'md' < 'none', 'sm', 'md', 'lg'",
        "  + * (jmix:droppableContent) = jmix:droppableContent",
        "",
        *raw_lines,
        "",
    ]


def type_block_semantic(comp, ns, mixns):
    """SEMANTIC archetype emission (redesign §10 + hybrid Option B, 2026-07-15):
    the composed supertype stack (base + mix:title + cta/media/seo mixins +
    mainResource/list/taxonomy) is taken VERBATIM from the manifest; only the
    archetype's OWN fields are emitted inline (mixin-provided image/cta/seo
    fields are NEVER repeated — they live in the shared mixins). Plus the layout
    choicelist + a typed childType.

    HYBRID: every type also composes {mixns}:sourceMarkup (hidden skeleton
    prop) so the default view can render the component's OWN captured markup —
    pixel-faithful, field edits reflow — while the semantic variant views stay
    available as authoring layouts. Contrib slot mixins carry per-node fields."""
    node = comp["nodeType"]
    ns = node.split(":")[0]
    sup = comp.get("supertypes") or _supertypes(comp.get("fields", []), mixns,
                                                comp.get("needsMainResource"))
    # CONTRACT (2026-07-16): CTAs are CHILD NODE TYPES, never a mixin — a mixin
    # exists at most once per node and cannot express repetition. Drop the cta
    # mixin from the composed stack; every type gets `+ * (ns:cta)` below.
    sup = [s for s in sup if s != f"{mixns}:cta"]
    sm = f"{mixns}:sourceMarkup"
    if sm not in sup:
        sup = list(sup) + [sm]
    head = f"[{node}] > {', '.join(sup)}"
    if comp.get("orderable") or comp.get("isContainer") or comp.get("childType"):
        head += " orderable"
    lines = [head]
    seen_body = False
    for f in comp.get("fields", []) or []:
        # ONE body per node — anything beyond is a child (gate-enforced)
        if f["name"].startswith("body"):
            if seen_body:
                continue
            seen_body = True
            f = {**f, "name": "body"}
        lines.append(field_line(f))
    if not seen_body:
        # CONTRACT v2 (2026-07-16): EVERY component owns a body richtext —
        # authorable content lives in PROPERTIES, never in the hidden skeleton.
        lines.append("  - body (string, richtext) i18n")
    lp = comp.get("layoutProperty")
    if isinstance(lp, dict):
        ll = layout_line(lp)
        if ll:
            lines.append(ll)
    # repetition = children on EVERY component type: the decomposition pass can
    # find repeating units inside ANY section (observed: hero/richText children
    # failed ConstraintViolation when only containers carried the rule), and
    # CTAs repeat anywhere. Both reusable child objects, 0..N, orderable.
    lines.append(f"  + * ({ns}:cardItem)")
    lines.append(f"  + * ({ns}:cta)")
    # the sub-nav excision (2026-07-23) splices a tree-driven subNavigation
    # CHILD inside content bands (sidebar+column layout) — without this rule
    # the loader's create fails ConstraintViolation on every service page
    lines.append(f"  + * ({ns}:subNavigation)")
    # BODY COMPOSITION (2026-08-03): a mainResource entity composes its body from
    # BANDS. Without this residual rule Jackrabbit refuses every band child with
    # `ConstraintViolationException: No child node definition found` (CLAUDE.md
    # rule 17), so the loader had no choice but to flatten the whole article into
    # one richtext — freezing its images, its video block and its section
    # structure out of the editor's reach.
    if comp.get("bodyChildren") or comp.get("needsMainResource"):
        lines.append(f"  + * ({mixns}:component)")
    return "\n".join(lines), ""


def _extra_contrib_slots(mixns, stats):
    """contrib_mixins blocks the ARCHETYPE shared CND does not already declare
    (contribImage duplicates the block above; contribBody's `body` prop would
    collide with the types' own body declaration). Keeps contribBody2..N,
    contribImage2..N, contribLabel..N, contribLink — the per-node slots the
    loader adds for POSITIONED extra runs (2026-07-20)."""
    if not stats:
        return []
    lines, keep, skip_hdr = contrib_mixins(mixns, stats), [], False
    exclude = (f"[{mixns}:contribBody]", f"[{mixns}:contribImage]")
    for l in lines:
        if l.startswith("["):
            skip_hdr = l.startswith(exclude)
        if not skip_hdr and not l.startswith("//"):
            keep.append(l)
    return keep


def emit_semantic(m, ns, mixns, proj, stats=None):
    """Assemble the CND for the archetype model — CONTRACT edition (2026-07-16):
    mixins are at-most-once property blocks composed into types; ALL repetition
    is child NODE TYPES (+ * (ns:cta) / (ns:cardItem)); one body per node; the
    structural set (jcrQuery/gridRow/mainResource/cta) always ships.
    Returns (shared_cnd, blocks, view_plans): shared_cnd = namespaces + mixins +
    structural types (settings/definitions.cnd); blocks = [(Short, cnd_text)]
    one per component for SDC placement in src/components/<Short>/definition.cnd."""
    import archetypes as ARCH
    ns_header = [
        "<jnt = 'http://www.jahia.org/jahia/nt/1.0'>",
        "<jmix = 'http://www.jahia.org/jahia/mix/1.0'>",
        "<mix = 'http://www.jcp.org/jcr/mix/1.0'>",
        f"<{ns} = 'https://jahia.com/{proj}/nt/1.0'>",
        f"<{mixns} = 'https://jahia.com/{proj}/mix/1.0'>",
        "",
    ]
    shared = ns_header + [
        "// base marker mixins (picker grouping + droppability)",
        *ARCH.base_mixin_cnd(mixns),
        "",
        "// HYBRID: captured markup rendered by the default view (hidden from editors)",
        f"[{mixns}:sourceMarkup] mixin",
        "  - skeleton (string, textarea) hidden",
        "  - skeletonOrig (string, textarea) hidden",
        "  - classMap (string) hidden",
        "",
        "// reusable AT-MOST-ONCE property blocks (a mixin can never repeat on a node)",
        *[l for l in ARCH.shared_mixin_cnd(mixns) if f"{mixns}:cta" not in l.split("\n")[0]
          or not l.startswith(f"[{mixns}:cta]")],
        "",
        "// single per-node optional image slot (added by the loader when carried)",
        f"[{mixns}:contribImage] mixin",
        "  - image (weakreference, picker[type='image']) < jmix:image",
        "  - imageOrig (string, textarea) hidden",
        "  - imageOrigRef (string) hidden",
        "",
        # POSITIONED extra slots (2026-07-20, structure-aware sweep): body2..N
        # and labelN runs living in a different wrapper than the body slot keep
        # their own field + in-place marker — the loader adds these mixins per
        # node; without them it silently drops the values (holes). Only the
        # slots the archetype CND does not already provide are emitted here.
        *_extra_contrib_slots(mixns, stats),
        "",
        "// ── reusable CONTENT OBJECTS: repetition is node types, never mixins ──",
        f"[{ns}:cta] > jnt:content, {mixns}:component, {mixns}:sourceMarkup",
        "  - j:linkType (string, choicelist[linkTypeInitializer]) = 'none' autocreated indexed=no",
        "  - linkLabel (string) i18n",
        "  - linkOrig (string) hidden",
        # COMPONENT MODEL (operator-approved 2026-07-21): every button, text
        # arrow and icon link is the SAME atom styled by an editable variant
        "  - variant (string, choicelist[resourceBundle]) = 'textArrow'",
        "",
        f"[{ns}:cardItem] > jnt:content, mix:title, {mixns}:component, {mixns}:sourceMarkup orderable",
        "  - body (string, richtext) i18n",
        "  - image (weakreference, picker[type='image']) < jmix:image",
        "  - imageOrig (string, textarea) hidden",
        "  - imageOrigRef (string) hidden",
        f"  + * ({ns}:cta)",
        # the sub-nav excision can land its subNavigation child inside a
        # cardItem (menu in a decomposed kid's body — admail class, 2026-07-23)
        f"  + * ({ns}:subNavigation)",
        "",
        "// ── structural set (rule 22): ALWAYS shipped ──",
        "// tree-driven breadcrumb — no content needed, rendered by the Layout",
        f"[{ns}:breadcrumb] > jnt:content, {mixns}:component",
        "",
        *query_and_grid_types(ns, mixns),
        "",
    ]
    # mainResource entity type: from the manifest if classified, else the default
    if not any(c.get("needsMainResource") for c in (m.get("components") or [])):
        shared += [
            "// entity/detail-page dimension: content listed via jcrQuery card views",
            f"[{ns}:article] > jnt:content, mix:title, {mixns}:component, "
            f"{mixns}:media, jmix:mainResource, {mixns}:sourceMarkup",
            "  - body (string, richtext) i18n",
            f"  + * ({ns}:cta)",
            "",
        ]
    blocks, view_plans = [], []
    view_plans.append({"component": "JCR Query", "nodeType": f"{ns}:jcrQuery",
                       "views": ["default.server.tsx"]})
    view_plans.append({"component": "Grid Row", "nodeType": f"{ns}:gridRow",
                       "views": ["default.server.tsx"]})
    skip = (":rawhtml", ":mainnavigation", ":jcrquery", ":gridrow")
    for c in (m.get("crossCutting", []) or []) + (m.get("components", []) or []):
        if c["nodeType"].lower().endswith(skip):
            continue  # structural/shared types live in settings, one definition
        blk, _ = type_block_semantic(c, ns, mixns)
        short = c["nodeType"].split(":")[-1]
        tags = [t for t, on in (("container", c.get("isContainer")),
                                ("mainResource", c.get("needsMainResource"))) if on]
        blocks.append((short, "\n".join(ns_header)
                       + f"// {c['name']} [{c.get('archetype')}] {tags}\n" + blk + "\n"))
        view_plans.append(views_for(c))
    full = "\n".join(shared) + "\n// ── components (SDC copies) ──\n" \
           + "\n".join(b for _, b in ((s, t.split("\n", len(ns_header))[-1]) for s, t in blocks))

    # DECLARE EVERY ITEM TYPE THE MANIFEST NAMES (2026-08-04). This emitter ships ONE
    # reusable item type, ns:cardItem, and grants it in every container. The manifest,
    # built from the archetypes, names items PER PARENT — ns:accordionItem,
    # ns:cardGridItem — because each archetype declares its own `child` key. Nothing
    # reconciled the two, and the load payload is written from the manifest by a step
    # that runs BEFORE this one, so it asked for 41 nodes of two types no CND declared:
    # the loader would have created what it could and thrown ConstraintViolation on the
    # rest, leaving a site that looks populated with holes in it (found pre-deploy by
    # probes/type-closure.py, which is the whole reason that gate exists).
    #
    # Declaring the aliases is the additive half of the fix — the payload does not have
    # to be recomputed and any project's naming is accommodated, whatever its archetypes
    # call their items. They mirror cardItem exactly, because in this model an item is a
    # skeleton node whose fields come from its slot mixins.
    declared = set(re.findall(r"^\[([\w:]+)\]", full, re.M))
    extra = []
    for c in m.get("components") or []:
        ct = c.get("childType")
        nt = ct.get("nodeType") if isinstance(ct, dict) else None
        if nt and nt not in declared and nt not in {x[0] for x in extra}:
            extra.append((nt, c.get("nodeType")))
    if extra:
        alias = ["", "// ── item types the manifest names per container (mirror cardItem) ──"]
        for nt, parent in extra:
            alias += [
                f"// items of {parent}",
                f"[{nt}] > jnt:content, mix:title, {mixns}:component, "
                f"{mixns}:sourceMarkup orderable",
                "  - body (string, richtext) i18n",
                "  - image (weakreference, picker[type='image']) < jmix:image",
                "  - imageOrig (string, textarea) hidden",
                "  - imageOrigRef (string) hidden",
                f"  + * ({ns}:cta)",
                "",
            ]
        full += "\n" + "\n".join(alias)
        # and grant them wherever the generic item is granted, or the parent cannot
        # hold the very children the payload puts in it
        # SCOPED to the declaring parent. A first version replaced every
        # `+ * (ns:cardItem)` line in the file, which granted accordionItem and
        # cardGridItem inside every container that allows a card — including
        # sdp:jcrQuery, which must hold no children at all. An item type belongs to
        # its own parent's block and nowhere else.
        for nt, parent in extra:
            if not parent:
                continue
            m = re.search(r"^\[" + re.escape(parent) + r"\][^\n]*\n(?:[ \t]+[^\n]*\n)*",
                          full, re.M)
            if not m:
                continue
            block = m.group(0)
            if f"+ * ({nt})" not in block:
                full = full.replace(block, block.rstrip("\n") + f"\n  + * ({nt})\n", 1)
        print(f"[cnd_emit] + {len(extra)} manifest-named item type(s): "
              + ", ".join(nt for nt, _ in extra))
    return full, blocks, view_plans


def write_sdc_and_sync(m, shared_full, blocks, ns, mixns, module_dir, manifest_path):
    """SDC placement + MANIFEST SYNC (operator finding 2026-07-16: the
    orchestrator's ComponentModelView reads component-manifest.json, which had
    drifted from the emitted CND). One source of truth: what the emitter wrote.
      - src/components/<Short>/definition.cnd   one per component
      - settings CND content = the SHARED part only (mixins + reusable objects +
        structural set) — merge_cnd consumes definitions.shared.cnd
      - the manifest's per-component entries are REWRITTEN to the emitted truth
        (supertypes minus cta-mixin, single body, childType -> ns:cardItem,
        cnd path, + * rules)."""
    import archetypes as ARCH  # noqa: F401  (kept for future emitted-model detail)
    TS_TYPES = {"string": "string", "richtext": "string", "long": "number",
                "double": "number", "boolean": "boolean",
                "weakreference": "JCRNodeWrapper", "date": "string"}
    comps_by_short = {c["nodeType"].split(":")[-1]: c
                      for c in (m.get("components", []) or []) + (m.get("crossCutting", []) or [])}
    for short, text in blocks:
        d = f"{module_dir}/src/components/{short[0].upper()}{short[1:]}"
        os.makedirs(d, exist_ok=True)
        with open(f"{d}/definition.cnd", "w", encoding="utf-8") as f:
            f.write(text)
        # types.ts (skill jahia-dev-create-view: Props from ./types.js; ALL
        # props optional — Jahia guarantees nothing at render time)
        comp = comps_by_short.get(short) or {}
        lines = ["import type { JCRNodeWrapper } from \"org.jahia.services.content\";",
                 "", "export interface Props {",
                 "  \"jcr:title\"?: string;", "  body?: string;",
                 "  image?: JCRNodeWrapper;", "  classMap?: string;"]
        for fdef in comp.get("fields") or []:
            nm = fdef["name"]
            if nm in ("body", "title", "image") or nm.startswith("j:"):
                continue
            base = (fdef.get("type") or "string").split(",")[0].strip()
            lines.append(f"  {json.dumps(nm)}?: {TS_TYPES.get(base, 'string')};")
        lines += ["}", ""]
        with open(f"{d}/types.ts", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    # shared-only CND for settings (workflow artifact; merge_cnd installs it)
    shared_only = shared_full.split("// ── components (SDC copies) ──")[0]
    wo = os.path.dirname(manifest_path)
    with open(f"{wo}/definitions.shared.cnd", "w", encoding="utf-8") as f:
        f.write(shared_only)
    mf = json.load(open(manifest_path))
    for c in (mf.get("components", []) or []) + (mf.get("crossCutting", []) or []):
        short = c["nodeType"].split(":")[-1]
        c["supertypes"] = [s for s in (c.get("supertypes") or []) if s != f"{mixns}:cta"]
        if f"{mixns}:sourceMarkup" not in c["supertypes"]:
            c["supertypes"].append(f"{mixns}:sourceMarkup")
        fields = [f for f in (c.get("fields") or []) if not re.match(r"body\d+$", f["name"])]
        if not any(f["name"] == "body" for f in fields):
            fields.append({"name": "body", "type": "string, richtext", "i18n": True})
        c["fields"] = fields
        c["childRules"] = ([f"+ * ({ns}:cardItem)"] if (c.get("isContainer") or c.get("childType")) else []) \
            + [f"+ * ({ns}:cta)"]
        if c.get("isContainer") or c.get("childType"):
            c["childType"] = {"nodeType": f"{ns}:cardItem", "name": "Card item",
                              "supertypes": ["jnt:content", "mix:title",
                                             f"{mixns}:component", f"{mixns}:sourceMarkup"],
                              "fields": [{"name": "body", "type": "string, richtext", "i18n": True},
                                         {"name": "image", "type": "weakreference, picker[type='image']"}]}
        c["cnd"] = f"src/components/{short[0].upper()}{short[1:]}/definition.cnd"
    mf["reusableTypes"] = [{"nodeType": f"{ns}:cta", "purpose": "repeatable CTA child"},
                           {"nodeType": f"{ns}:cardItem", "purpose": "repeatable item child"}]
    mf["structuralSet"] = [f"{ns}:jcrQuery", f"{ns}:gridRow", f"{ns}:rawHtml",
                           f"{ns}:mainNavigation"] \
        + ([f"{ns}:article"] if not any(x.get("needsMainResource")
                                        for x in mf.get("components", [])) else [])
    json.dump(mf, open(manifest_path, "w"), indent=2, ensure_ascii=False)
    return mf


def views_for(comp):
    """Deterministic view plan for a component."""
    node = comp["nodeType"]
    views = ["default.server.tsx"]
    if comp.get("needsMainResource"):
        # A mainResource is rendered in exactly two situations, and the model should
        # name both (operator, 2026-08-04): a jcrQuery LISTS it — asking Jahia for
        # `subNodeView = 'card'`, which is what sdp:jcrQuery declares — and its own URL
        # renders it FULL PAGE. The card view is what carries the link back to
        # fullPage, so it is the hinge of the whole listing story.
        #
        # It was missing: these types emitted default + fullPage only, so every listing
        # asked for a `card` view that did not exist and silently fell back to
        # `default`. The docstring above still calls default "card/teaser", which is
        # where the ambiguity came from — `default` renders the entity in whatever
        # context it happens to sit, and a listing card is a deliberate, different
        # rendering (image, title, date, link). Naming it makes the contract legible.
        views.append("card.server.tsx")
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
    ap.add_argument("--module-dir",
                    help="module root for SDC per-component definition.cnd placement "
                         "(archetype model; default projects/<project>)")
    ap.add_argument("--content-load",
                    help="content-load.json — sizes body..bodyN per type from the "
                         "OBSERVED lift (P2.5 wired-only CND for skeleton types)")
    args = ap.parse_args()

    m = json.load(open(args.manifest))
    ns, mixns, proj = args.ns, args.mixns, args.project

    # SEMANTIC archetype model (redesign §10, hybrid Option B): composed mixins +
    # semantic fields + hidden sourceMarkup + per-node contrib slots (sized from
    # the observed lift). Auto-detected from the manifest so the skeleton path
    # stays the default for skeleton manifests.
    if m.get("model") == "archetype":
        # slot sizing (2026-07-20, structure-aware sweep): the payload may now
        # carry POSITIONED body2..N/labelN runs (fragments living in a
        # different wrapper than the body slot) — their contribBody/LabelN
        # mixins must exist or the loader silently drops the values and the
        # skeleton markers render holes.
        arch_stats = (run_stats_from_content_load(args.content_load, m)
                      if args.content_load else None)
        cnd, blocks, view_plans = emit_semantic(m, ns, mixns, proj, stats=arch_stats)
        if args.out_cnd:
            open(args.out_cnd, "w").write(cnd)
        else:
            print(cnd)
        if args.out_views:
            json.dump({"project": proj, "namespace": ns, "views": view_plans},
                      open(args.out_views, "w"), indent=2, ensure_ascii=False)
        module_dir = args.module_dir or f"projects/{proj}"
        if os.path.isdir(f"{module_dir}/src"):
            write_sdc_and_sync(m, cnd, blocks, ns, mixns, module_dir, args.manifest)
            print(f"[cnd_emit] SDC: {len(blocks)} definition.cnd file(s) -> "
                  f"{module_dir}/src/components/ + shared -> definitions.shared.cnd; "
                  f"manifest synced to the EMITTED model", file=sys.stderr)
        nt = len(m.get("components", []) or []) + len(m.get("crossCutting", []) or [])
        print(f"[cnd_emit] SEMANTIC model (contract): {nt} archetype types -> "
              f"{args.out_cnd or '(stdout)'}", file=sys.stderr)
        return

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
