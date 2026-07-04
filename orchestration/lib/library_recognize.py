#!/usr/bin/env python3
"""library_recognize.py — P6.3: the GENERIC library recognizer for the recompose
stage. Generalizes the P6.2 logo-wall prototype (decompose_logowall.py) into a
project-agnostic, deterministic recognizer that maps a DOM subtree onto the base
component library (LIBRARY-SPEC §1: logoWall/logo, cardGrid/card, section, …).

DOCTRINE (MODULARITY-PLAN §5b — FIDELITY-FIRST):
  Promote a subtree to a typed COMPOSABLE library component ONLY when the
  composed render is reproducible from the SOURCE markup (each atom carries its
  verbatim `orig` markup + source classes, rule 26 — byte-exact by construction).
  Otherwise return None and the caller keeps the existing skeleton/rawHtml path
  (fidelity never regresses; composability rises with library coverage).

  This is NEVER content generation — it RE-STRUCTURES captured markup into typed
  nodes. Every atom stores the exact source facts (classes, orig media markup,
  href) so an unedited node is identical to the frozen skeleton.

The output is a `LibraryPlan` (a plain dict) that the loader turns into REAL
composable nodes (container + typed atom children), EDIT-only. Recognizers are
tried in order; the first faithful match wins. When none match -> None.

Generalization lessons applied (from the P6.2 report):
  1. Structural recognizer — keys on "element wraps media/link" + repeated
     same-signature siblings >=3, never on a project-specific class name.
  2. Load library-native — atoms carry asrmix:media/cta facts (image file, alt,
     href, orig markup), the loader wires DAM weakref + jmix:externalLink.
  3. Skin = SOURCE classes — the container plan records the source wrapper class
     chain + per-atom anchor/wrapper classes so the VIEW reproduces them (the
     deployed logoWall/logo views skin off source classes, not generic CSS).
  4. Spacers travel with the atom — a break-*/empty <div> that FOLLOWS an atom is
     recorded on that atom (flex-wrap breakpoints survive reorder/add).
  5. Repeated <p>/<h*>/<ul> are a TEXT RUN, never items (rule 24) — the media/link
     wrap requirement structurally excludes them (a paragraph wraps neither).

Public API:
  recognize(el, ns="asr") -> LibraryPlan | None
    el       : a bs4 Tag (a vision root or a promoted top group)
    returns  : {"kind","nodeType","container":{...},"children":[{...}], "atomType",
                "sourceClasses":[...]} or None
"""
import re

from bs4 import Tag

# spacer <div> classes that force a flex line break at a breakpoint (load-bearing
# layout — flex-basis:100%). A classless <div> spacer carries no CSS but travels
# in the container skeleton as a serialization artifact.
BREAK_CLASSES = {"break-mobile", "break-tablet", "break-desktop"}

# minimum repeated same-signature siblings to treat as a composable repeater
MIN_REPEAT = 3


# ── small structural helpers (agnostic — no project vocabulary) ──────────────

def _classes(el):
    c = el.get("class") if isinstance(el, Tag) else None
    if not c:
        return []
    return c if isinstance(c, list) else str(c).split()


def _class_sig(el):
    """Signature for repeated-sibling detection: tag + sorted non-empty classes."""
    return (el.name, tuple(sorted(_classes(el))))


def _child_tags(el):
    return [c for c in el.children if isinstance(c, Tag)]


def _wraps_media(el):
    """True if el's subtree contains an <img>/<picture> (a logo/image atom)."""
    return el.find(["img", "picture"]) is not None


def _has_href(el):
    return el.name == "a" and bool((el.get("href") or "").strip())


def _find_repeater(root):
    """Find the DEEPEST wrapper whose direct children contain a run of >=MIN_REPEAT
    same-signature <a> siblings that each wrap media. Returns (wrapper, [anchors])
    or (None, None). Deterministic: first such wrapper in document order.

    Keying on <a>-wrapping-<img> (structural) is what excludes a <p>/<h*> text run
    from ever becoming items (rule 24) — a paragraph wraps neither a link nor media.
    """
    for node in [root] + root.find_all(True):
        kids = _child_tags(node)
        anchors = [k for k in kids if _has_href(k) and _wraps_media(k)]
        if len(anchors) < MIN_REPEAT:
            continue
        # the anchors must be same-signature (a uniform logo/image row)
        sig_counts = {}
        for a in anchors:
            sig_counts.setdefault(_class_sig(a), []).append(a)
        best = max(sig_counts.values(), key=len)
        if len(best) >= MIN_REPEAT:
            return node, best
    return None, None


# ── media/link fact extraction (fidelity — rule 26 verbatim-default) ─────────

def _img_facts(anchor):
    """The fidelity facts of one <a><picture><img></a> logo/image atom.
    `orig` = the exact inner markup (picture or img) — rendered VERBATIM by the
    view while the picked image weakref still points at the DAM copy of it."""
    img = anchor.find("img")
    if img is None:
        return None
    src = (img.get("src") or img.get("data-src") or "").strip()
    if not src or src.startswith("data:"):
        return None
    pic = anchor.find("picture")
    orig_el = pic if pic is not None else img
    return {
        "src": src,                                   # source URL (loader -> filename_for)
        "alt": img.get("alt", "") or "",
        "title": img.get("title", "") or "",
        "orig": str(orig_el),                          # exact media markup (verbatim default)
        "href": (anchor.get("href") or "").strip(),
        "ariaLabel": anchor.get("aria-label", "") or "",
        "anchorClass": " ".join(_classes(anchor)),     # source class -> reproduced by view
    }


def _source_class_chain(root, repeater):
    """Record the wrapper class chain from `root` down to (and including) the
    repeater, so the container view can reproduce the source layout markup
    (skin = source classes). Returns [ {tag, class} ... ] outermost-first."""
    chain = []
    node = root
    # descend recording each element until we pass the repeater
    stack = [root]
    seen = set()
    cur = root
    # collect ancestors of the repeater within root (inclusive of root & repeater)
    path = []
    n = repeater
    while n is not None:
        path.append(n)
        if n is root:
            break
        n = n.parent
    path.reverse()
    for el in path:
        chain.append({"tag": el.name, "class": " ".join(_classes(el))})
    return chain


# ── recognizer: LOGO WALL / IMAGE ROW (P6.2 pattern, generalized) ────────────

def _recognize_logowall(root, ns):
    """A wrapper whose repeated same-signature <a>-wrapping-<img> siblings (>=3)
    form a wall of logos/images -> ns:logoWall of ns:logo atoms.

    The odd-one-out leading anchor with its OWN distinct class (e.g. master-logo)
    in a sibling wrapper -> the fixed `master` slot. Break-* spacers that follow
    an anchor travel with that atom.

    Faithful by construction: each atom stores its verbatim media `orig` + source
    anchor class; the container stores the source wrapper class chain. The loader
    creates real ns:logoWall + ns:logo nodes (asrmix:media/cta)."""
    repeater, anchors = _find_repeater(root)
    if repeater is None:
        return None

    # walk the repeater's direct children in document order: same-signature
    # media-wrapping anchors become logo atoms; a break-*/empty <div> that FOLLOWS
    # an anchor is recorded on that atom's spacer.
    rep_sig = _class_sig(anchors[0])
    logos = []
    pending = None
    extra_between = []          # non-atom, non-spacer markup inside the repeater
    for ch in _child_tags(repeater):
        if _has_href(ch) and _wraps_media(ch) and _class_sig(ch) == rep_sig:
            facts = _img_facts(ch)
            if facts is None:
                # an anchor we can't extract faithfully -> abort promotion
                return None
            facts["variant"] = "brand"
            facts["breakClass"] = ""
            logos.append(facts)
            pending = facts
        elif ch.name == "div" and not _child_tags(ch) and not (ch.get_text(strip=True)):
            cls = [c for c in _classes(ch) if c in BREAK_CLASSES]
            if pending is not None:
                pending["breakClass"] = " ".join(cls)   # spacer travels with the atom
            # classless/empty spacer with no pending atom: layout artifact, dropped
        else:
            # any OTHER content inside the repeater (heterogeneous) — promoting
            # would drop it. Fidelity-first: refuse (skeleton fallback handles it).
            if ch.get_text(strip=True) or _wraps_media(ch):
                extra_between.append(ch)

    if len(logos) < MIN_REPEAT:
        return None
    if extra_between:
        return None            # non-uniform repeater -> not a faithful logoWall

    # master slot: an anchor-wrapping-image with a DIFFERENT signature that sits
    # BEFORE the repeater under the same root (the P6.2 master-logo). Optional.
    master = None
    for a in root.find_all("a"):
        if a in (l for l in anchors):
            continue
        if _class_sig(a) == rep_sig:
            continue
        if _has_href(a) and _wraps_media(a):
            # must be outside the repeater
            if repeater in a.parents or a is repeater:
                continue
            mf = _img_facts(a)
            if mf is not None:
                mf["variant"] = "master"
                mf["breakClass"] = ""
                master = mf
            break

    src_classes = _source_class_chain(root, repeater)
    return {
        "kind": "logoWall",
        "nodeType": f"{ns}:logoWall",
        "atomType": f"{ns}:logo",
        "container": {
            # extra classes on the repeater's parent chain, kept so the view
            # reproduces the exact source wrapper (skin = source classes)
            "sourceClasses": src_classes,
            "rootClass": " ".join(_classes(root)),
            "repeaterClass": " ".join(_classes(repeater)),
            "heading": "",
        },
        "master": master,
        "children": logos,
        # every atom carries a link + image -> all editable (vs 1/N in the skeleton)
        "editableLinks": sum(1 for l in logos if l["href"]) + (1 if master and master["href"] else 0),
        "editableImages": len(logos) + (1 if master else 0),
    }


# ── recognizer registry (ordered; first faithful match wins) ─────────────────

RECOGNIZERS = [
    _recognize_logowall,
]


def recognize(el, ns="asr"):
    """Try each library recognizer on `el`; return the first LibraryPlan or None.
    None means no faithful library mapping -> caller keeps skeleton/rawHtml
    (fidelity-first). `el` is a bs4 Tag (a vision root or promoted top group)."""
    if not isinstance(el, Tag):
        return None
    for rec in RECOGNIZERS:
        try:
            plan = rec(el, ns)
        except Exception:
            plan = None
        if plan is not None:
            return plan
    return None


def library_gap_reason(el):
    """Best-effort human-readable reason a subtree did NOT match any recognizer —
    logged so the fallback rate feeds library growth (a 'library gap')."""
    if not isinstance(el, Tag):
        return "not-an-element"
    rep, anchors = _find_repeater(el)
    if rep is None:
        n_a = len(el.find_all("a", href=True))
        n_img = len(el.find_all(["img", "picture"]))
        return f"no-uniform-media-repeater (anchors={n_a}, media={n_img})"
    return "repeater-found-but-heterogeneous-or-unliftable"


if __name__ == "__main__":
    import argparse
    import json
    import sys

    from bs4 import BeautifulSoup

    ap = argparse.ArgumentParser(description="Probe the library recognizer on an HTML fragment")
    ap.add_argument("fragment", help="path to an html fragment")
    ap.add_argument("--ns", default="asr")
    a = ap.parse_args()
    soup = BeautifulSoup(open(a.fragment, encoding="utf-8").read(), "html.parser")
    root = next((c for c in soup.children if isinstance(c, Tag)), None)
    if root is None:
        sys.exit("no root element")
    plan = recognize(root, a.ns)
    if plan is None:
        print(f"NO MATCH — {library_gap_reason(root)}")
    else:
        summary = {k: (v if k not in ("children", "master") else
                       (len(v) if isinstance(v, list) else "1")) for k, v in plan.items()}
        print(json.dumps(summary, indent=2))
