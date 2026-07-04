#!/usr/bin/env python3
"""vision_extract.py — the VISION-DRIVEN EXTRACTION ADAPTER bridge (P4).

The missing link that makes the vision component model actually DRIVE content
extraction. Without it, extract_content.semantic_page re-derives its own
component boundaries via semantic_extract.extract_page — an independent walk
that COLLAPSES on client-rendered AEM SPAs (no <main> element -> body anchor ->
homogeneity heuristic sees N modal/script divs -> 0 components). The vision
manifest's DOM boundaries were read but never used for extraction (only for
instanceTypeMap / childType). Census on the discoverasr live run before this
bridge: 0 typed / 1631 instances, 260 anonymous lifted-raw, 1368 verbatim
rawHtml, 649 media unplaced inside verbatim blobs.

This module resolves each vision component's ROOT element (identified by the
segment probe in `segment/<slug>.dom.html`, keyed by data-seg) into the LIVE
local-mirror page DOM, so the EXISTING decompose_group / skeleton machinery can
promote it. The bridge is site-agnostic — no discoverasr-specific logic.

Two mapping paths, both fully deterministic:

  * SEGMENTED page: the segmentation's `rootId` -> the data-seg-annotated element
    in `<slug>.dom.html` (the browser's post-hydration serialization). That DOM
    is NOT byte-identical to the certified local-mirror (`<slug>.html`) — the
    browser injects consent/beacon scripts, random ids, `.ta-display-none`
    styles, etc. So we map by the element's STRUCTURAL nth-of-type path from
    <body> (proven stable across the two serializations on every discoverasr
    component root) and re-extract from the MIRROR element. This is what keeps
    the byte-identity self-check honest: decompose_group runs on the mirror
    element (what the ground-truth gate renders), never on the dom.html.

  * UNSEGMENTED page (vision samples only ~5 of 20 pages): match vision
    components by a deterministic SIGNATURE derived from their mirror root
    elements on segmented pages — (tag, sorted non-layout class tokens). A match
    must still pass the byte self-check before promotion (done by the caller);
    no match -> the existing verbatim rawHtml fallback. Page-wrapper signatures
    (xfpage/basicpage/aem-grid/…) and container-of-components matches are
    rejected so a single match can never engulf the whole page.

Public API (all pure functions over bs4 trees + JSON):
  has_vision_segmentations(project) -> bool          # adapter selector
  load_signature_index(project)     -> {sig: name}   # from segmented pages
  resolve_segmented(project, slug, mirror_soup)      # -> [(name, mirror_el)]
  match_unsegmented(sig_index, mirror_soup)          # -> [(name, mirror_el)]
"""
import json
import os
import re

from bs4 import BeautifulSoup, Tag

import semantic_extract as SE


# ── DOM structural path (dom.html element -> mirror element) ──────────
#
# nth-of-type index among same-tag siblings, from the element up to <body>.
# Proven byte-stable across the post-hydration serialization (dom.html, with
# data-seg + injected consent scripts) and the certified local-mirror on every
# discoverasr vision component root (11/12 also text-identical; the 12th differs
# only by lazy-image whitespace, structurally identical).

def struct_path(el):
    parts = []
    n = el
    while isinstance(n, Tag) and n.parent is not None and n.name != "html":
        p = n.parent
        sibs = [s for s in p.children if isinstance(s, Tag) and s.name == n.name]
        try:
            idx = sibs.index(n)
        except ValueError:
            idx = -1
        parts.append((n.name, idx))
        if n.name == "body":
            break
        n = p
    return list(reversed(parts))


def resolve_path(path, mirror_soup):
    """Follow a struct_path in the mirror DOM. Returns the Tag or None."""
    if not path:
        return None
    node = None
    for tag, idx in path:
        if tag == "body":
            node = mirror_soup.find("body")
            continue
        if node is None:
            return None
        sibs = [s for s in node.children if isinstance(s, Tag) and s.name == tag]
        if idx < 0 or idx >= len(sibs):
            return None
        node = sibs[idx]
    return node


# ── Component signature (unsegmented-page matching) ───────────────────
#
# The stable identity of a component root across pages: its tag + the set of its
# NON-LAYOUT class tokens (CSS-module hashes stripped by clean_token, layout
# scaffolding dropped by is_layout_class — the same normalization the heuristic
# role uses). Deterministic, order-independent, no vision call.

# Page/structure wrapper class tokens that must NEVER anchor a component — a root
# carrying one engulfs the entire page (AEM xfpage/basicpage, the aem-Grid root,
# JSP parsys roots). Reject them from the signature index outright.
_PAGE_WRAP = {
    "xfpage", "basicpage", "rootpage", "structure", "root", "aem-grid",
    "aem-page", "par", "iparsys", "contentpar", "responsivegrid",
}


def component_signature(el):
    """(tag, sorted non-layout cleaned class tokens). Empty-class -> tag only."""
    cls = [SE.clean_token(c) for c in SE.classes_of(el)]
    cls = tuple(sorted(c for c in cls if not SE.is_layout_class(c)))
    return (el.name, cls)


def _is_page_wrap(sig):
    return any(c.lower() in _PAGE_WRAP for c in sig[1])


# ── Adapter selection ─────────────────────────────────────────────────

def _seg_dir(project):
    return f"projects/{project}/workflow-output/segment"


def _passing_segmentations(project):
    """Segmentation JSONs whose page PASSED the gate (gatePass or adjudicated) AND
    whose dom.html exists (the live run may still be writing them — mirror
    segment2manifest's own skip). Returns [(slug, seg_dict, dom_path)]."""
    d = _seg_dir(project)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".segmentation.json"):
            continue
        try:
            s = json.load(open(os.path.join(d, fn)))
        except Exception:
            continue
        if not (s.get("gatePass") is True or s.get("adjudicated") is True):
            continue
        slug = s.get("slug")
        dom_p = os.path.join(d, f"{slug}.dom.html")
        if slug and os.path.isfile(dom_p):
            out.append((slug, s, dom_p))
    return out


def has_vision_segmentations(project):
    """True iff at least one PASSING vision segmentation (with its dom.html) exists.
    This is the automatic adapter selector — no flag, no site-specific config."""
    return bool(_passing_segmentations(project))


# ── Per-page resolution ───────────────────────────────────────────────

def _vision_components(seg):
    """Non-chrome vision components of a segmentation (chrome -> absolute areas,
    handled separately by resolve_chrome)."""
    return [c for c in seg.get("components", []) if c.get("kind") != "chrome"]


def resolve_chrome(project, slug, mirror_soup):
    """Resolve the page's CHROME vision components (kind='chrome': header/footer/
    nav) into the mirror DOM. Returns [(area, vision_name, mirror_el)] where area
    is inferred from the name (header/footer/nav). These become area-flagged
    rawHtml singletons routed to /home/<area> (migration rule 16) — removing
    their nav/footer text from the page's contribution denominator, exactly as
    the semantic adapter's chromePassthrough does."""
    d = _seg_dir(project)
    seg_p = os.path.join(d, f"{slug}.segmentation.json")
    dom_p = os.path.join(d, f"{slug}.dom.html")
    if not (os.path.isfile(seg_p) and os.path.isfile(dom_p)):
        return []
    try:
        seg = json.load(open(seg_p))
    except Exception:
        return []
    dom = BeautifulSoup(open(dom_p, errors="replace").read(), "lxml")
    by_seg = {el.get("data-seg"): el for el in dom.find_all(attrs={"data-seg": True})}
    out, seen = [], set()
    for c in seg.get("components", []):
        if c.get("kind") != "chrome":
            continue
        r = by_seg.get(str(c.get("rootId")))
        if r is None:
            continue
        mp = resolve_path(struct_path(r), mirror_soup)
        if mp is None or id(mp) in seen:
            continue
        seen.add(id(mp))
        name = (c.get("name") or "").lower()
        area = "footer" if "footer" in name else "nav" if "nav" in name else "header"
        out.append((area, c.get("name") or "chrome", mp))
    return out


def load_chrome_signatures(project):
    """{signature: (area, name)} for chrome components across segmented pages —
    so an unsegmented page's header/footer are routed to areas by signature too."""
    idx = {}
    for slug, seg, _dom_p in _passing_segmentations(project):
        mir_p = f"projects/{project}/workflow-output/local-mirror/{slug}.html"
        if not os.path.isfile(mir_p):
            continue
        try:
            mir = BeautifulSoup(open(mir_p, encoding="utf-8", errors="ignore").read(), "lxml")
        except Exception:
            continue
        for area, name, mp in resolve_chrome(project, slug, mir):
            sig = component_signature(mp)
            if sig[1] and not _is_page_wrap(sig):
                idx.setdefault(sig, (area, name))
    return idx


def match_chrome_unsegmented(chrome_index, mirror_soup):
    """Chrome roots on an unsegmented page, by signature. Returns [(area, name, el)]."""
    body = mirror_soup.find("body")
    if body is None:
        return []
    out, seen = [], set()
    for el in body.find_all(True):
        sig = component_signature(el)
        if sig in chrome_index and id(el) not in seen:
            # skip if nested inside an already-matched chrome root
            if any(id(e2) in seen for e2 in el.parents):
                continue
            seen.add(id(el))
            area, name = chrome_index[sig]
            out.append((area, name, el))
    return out


def resolve_segmented(project, slug, mirror_soup):
    """For a page that HAS its own passing segmentation, resolve every non-chrome
    vision component root into the mirror DOM. Returns an ordered, de-duplicated,
    non-nested list of (vision_name, mirror_el). Order = document order in the
    mirror (so the emitted regions follow the page)."""
    d = _seg_dir(project)
    seg_p = os.path.join(d, f"{slug}.segmentation.json")
    dom_p = os.path.join(d, f"{slug}.dom.html")
    if not (os.path.isfile(seg_p) and os.path.isfile(dom_p)):
        return []
    try:
        seg = json.load(open(seg_p))
    except Exception:
        return []
    if not (seg.get("gatePass") is True or seg.get("adjudicated") is True):
        return []
    dom = BeautifulSoup(open(dom_p, errors="replace").read(), "lxml")
    by_seg = {el.get("data-seg"): el for el in dom.find_all(attrs={"data-seg": True})}
    resolved = []
    seen = set()
    for c in _vision_components(seg):
        r = by_seg.get(str(c.get("rootId")))
        if r is None:
            continue
        mp = resolve_path(struct_path(r), mirror_soup)
        if mp is None or id(mp) in seen:
            continue
        seen.add(id(mp))
        resolved.append((c.get("name") or "component", mp))
    return _dedup_non_nested(resolved, mirror_soup)


def load_signature_index(project):
    """Learn a {signature: vision_name} index from ALL passing segmented pages —
    each non-chrome component root's mirror-element signature -> its vision name.
    First page to define a signature wins (stable across a sorted file walk).
    Page-wrapper and empty-class signatures are excluded."""
    idx = {}
    for slug, seg, _dom_p in _passing_segmentations(project):
        mir_p = f"projects/{project}/workflow-output/local-mirror/{slug}.html"
        if not os.path.isfile(mir_p):
            continue
        try:
            mir = BeautifulSoup(open(mir_p, encoding="utf-8", errors="ignore").read(), "lxml")
        except Exception:
            continue
        for name, mp in resolve_segmented(project, slug, mir):
            sig = component_signature(mp)
            if not sig[1] or _is_page_wrap(sig):
                continue  # empty-class or page-wrapper: too generic to match on
            idx.setdefault(sig, name)
    return idx


def match_unsegmented(sig_index, mirror_soup):
    """For a page WITHOUT its own segmentation, find component roots by signature.
    Returns an ordered, non-nested list of (vision_name, mirror_el).

    Guards (so one match can never swallow the page):
      - page-wrapper signatures are absent from the index by construction;
      - a candidate that CONTAINS >=2 other candidates is a container-of-
        components, not a leaf component — dropped (its inner matches survive);
      - among survivors, only the OUTERMOST of any nested pair is kept."""
    body = mirror_soup.find("body")
    if body is None:
        return []
    cands = []
    for el in body.find_all(True):
        sig = component_signature(el)
        if sig in sig_index:
            cands.append((sig_index[sig], el))
    if not cands:
        return []
    cand_els = [e for _, e in cands]
    # drop engulfers (container-of-components)
    kept = []
    for name, el in cands:
        contains = sum(1 for e2 in cand_els if e2 is not el and e2 in el.parents)
        if contains < 2:
            kept.append((name, el))
    return _dedup_non_nested(kept, mirror_soup)


def decompose_group_with_items(group, items, lift_titles=True):
    """Like semantic_extract.decompose_group, but the ITEMS are SUPPLIED (the
    resolved vision component roots) instead of auto-detected by find_repeated_items.

    Each supplied item -> a child payload (own skeleton + lifted title/body*/media/
    link), replaced in the group skeleton by a {{child:i}} marker. Group-level runs
    are lifted around the banned item subtrees. MUTATES `group`. Byte self-checked:
    ok=False means recompose(skeleton, fields, children) != the group's original
    serialization and the caller MUST load the original verbatim (rule 23).

    This is the same mechanism decompose_group uses internally — factored here so
    the vision adapter can promote a shared wrapper as a container whose children
    are the vision components, keeping every emitted region balanced + byte-exact
    (splitting the wrapper into sibling instances cannot preserve nesting)."""
    from bs4 import NavigableString

    # items must be in document order and mutually non-nested (a marker replacing an
    # ancestor would swallow a nested item's marker). Drop any item nested in another.
    items = [it for it in items
             if not any(other is not it and other in it.parents for other in items)]

    original = str(group)

    def lift_scope(scope, banned, titles):
        f = {}
        t = SE.lift_title(scope, banned) if titles else None
        if t:
            f["title"] = t
        f.update(SE.lift_bodies(scope, banned))
        media, media_total = SE.lift_media(scope, banned)
        link, link_total = SE.lift_link(scope, banned, f)
        return {"fields": f, "media": media, "mediaTotal": media_total,
                "link": link, "linkTotal": link_total}

    children = []
    for it in items:
        pl = lift_scope(it, set(), lift_titles)
        pl["el"] = it
        children.append(pl)
    banned_ids = set()
    for it in items:
        SE.ban_subtree(banned_ids, it)
    # group-level: titles NOT lifted (the container is rawHtml-ish / its heading may
    # belong to an item); its residual text runs still become editable body* fields
    top = lift_scope(group, banned_ids, titles=False)
    for i, ch in enumerate(children):
        ch["skeleton"] = str(ch["el"])
        ch["el"].replace_with(NavigableString(SE.CHILD_MARK % i))
        del ch["el"]
    skeleton = str(group)
    out = {"ok": None, "original": original, "skeleton": skeleton,
           "fields": top["fields"], "media": top["media"],
           "mediaTotal": top["mediaTotal"], "link": top["link"],
           "linkTotal": top["linkTotal"], "children": children}
    out["ok"] = SE.recompose_group(skeleton, top["fields"], children,
                                   media=top["media"], link=top["link"]) == original
    return out


def _dedup_non_nested(pairs, mirror_soup):
    """Keep only outermost of any nested pair; return in document order. `pairs`
    is [(name, el)]. Document order = order of appearance in a full-tree walk."""
    els = [e for _, e in pairs]
    surviving = set(id(e) for e in els)
    keep = []
    for name, el in pairs:
        if any(e2 is not el and id(e2) in surviving and el in e2.parents for e2 in els):
            continue  # nested inside another survivor
        keep.append((name, el))
    # document order: index by position in a body pre-order walk
    body = mirror_soup.find("body") or mirror_soup
    order = {}
    for i, node in enumerate(body.find_all(True)):
        order[id(node)] = i
    keep.sort(key=lambda ne: order.get(id(ne[1]), 1 << 30))
    # final safety: drop exact-duplicate element ids
    out, seen = [], set()
    for name, el in keep:
        if id(el) in seen:
            continue
        seen.add(id(el))
        out.append((name, el))
    return out
