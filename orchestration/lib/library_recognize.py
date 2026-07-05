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

# minimum CANONICAL (de-cloned) slides to treat a track as a carousel. A carousel
# is meaningful with 2 slides (unlike a logo wall which needs >=3 to be a "wall").
MIN_SLIDES = 2

# clone/duplicate CSS-class markers a JS carousel injects for the infinite-scroll
# illusion (swiper/slick/owl + the custom asr-content-slider). Any slide carrying
# one of these — or a BEM `*--cloned`/`*__clone*` class — is a NON-canonical clone.
# These are matched against the FULL class string (substring + token), so
# `cmp-carousel__item--cloned` and a bare `cloned` token both hit.
CLONE_CLASS_TOKENS = {
    "cloned", "clone", "slick-cloned", "swiper-slide-duplicate",
    "swiper-slide-duplicate-prev", "swiper-slide-duplicate-next",
    "owl-clone", "is-clone", "js-clone",
}
CLONE_CLASS_SUBSTR = ("--cloned", "__clone", "-clone", "duplicate")

# inline-style properties that encode a TRANSIENT JS SCROLL/VISIBILITY STATE and
# must be stripped before an element becomes a persisted content node — otherwise
# the node would freeze one frame of a scroll animation (rule: strip JS state).
# `width`/`margin-left` on a JS-sized slide track are transient too (the JS lays
# the flex row out in px); we strip the whole positional set. We NEVER touch
# non-positional inline styles (colors, backgrounds) — those are source design.
JS_STATE_STYLE_PROPS = {
    "transform", "-webkit-transform", "transition", "-webkit-transition",
    "translate", "margin-left", "margin-right", "left", "right", "top", "bottom",
    "opacity", "display", "visibility", "width", "min-width", "max-width",
    "will-change",
}


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


# ── cloned-slide dedup + JS-state strip (carousel fidelity, P6.3-bis) ─────────

def _is_clone(el):
    """True if `el` is a JS-injected CLONE of a canonical slide (infinite-scroll
    illusion) — NOT contributor content, must be excluded from the child count.

    Deterministic marker union (never a project class name):
      - a clone CSS-class token (cloned / slick-cloned / swiper-slide-duplicate /
        owl-clone …) or a BEM `*--cloned`/`*__clone`/`-clone`/`duplicate` class;
      - aria-hidden="true" (swiper/slick hide clones from AT);
      - a `data-swiper-slide-index` that DUPLICATES a canonical index — handled
        separately in the dedup pass (needs sibling context)."""
    cls = _classes(el)
    if any(c in CLONE_CLASS_TOKENS for c in cls):
        return True
    joined = " ".join(cls)
    if any(sub in joined for sub in CLONE_CLASS_SUBSTR):
        return True
    if (el.get("aria-hidden") or "").strip().lower() == "true":
        return True
    return False


def _dedup_clones(slides):
    """Return the CANONICAL slides in document order, dropping JS clones.

    Two-pass:
      1) marker-based: drop any slide `_is_clone` flags (class/aria-hidden).
      2) index-based: if slides carry `data-swiper-slide-index` (swiper), keep the
         FIRST occurrence of each index (later duplicates are clones even when the
         class marker is absent).
    Falls back to the input unchanged if EVERY slide looks like a clone (a
    misdetection guard — never return an empty canonical set)."""
    kept = [s for s in slides if not _is_clone(s)]
    # swiper index dedup on the survivors (and, if markers dropped everything,
    # on the full list so we still de-duplicate an all-marked track)
    pool = kept if kept else slides
    seen_idx = set()
    out = []
    for s in pool:
        idx = s.get("data-swiper-slide-index")
        if idx is not None:
            if idx in seen_idx:
                continue
            seen_idx.add(idx)
        out.append(s)
    return out if out else slides


_STYLE_DECL_RE = re.compile(r"\s*([-\w]+)\s*:\s*[^;]*;?")


def _strip_js_state(markup):
    """Return `markup` (an HTML string) with TRANSIENT JS scroll/visibility state
    removed from inline `style=""` attributes, on EVERY element in the fragment.
    A slide the JS froze at `style="transform: translate3d(...); opacity: 1;
    display: block; width: 1200px;"` becomes clean persisted content; a
    non-positional inline style (a source background/color) is preserved.

    Parses with the same html.parser BeautifulSoup the pipeline uses so the
    re-serialization is byte-idempotent for the surviving markup."""
    from bs4 import BeautifulSoup
    frag = BeautifulSoup(markup, "html.parser")
    for el in frag.find_all(style=True):
        decls = []
        for prop, decl in _extract_decls(el.get("style") or ""):
            if prop.lower() in JS_STATE_STYLE_PROPS:
                continue
            decls.append(decl)
        cleaned = "; ".join(d.rstrip(";").strip() for d in decls if d.strip())
        if cleaned:
            el["style"] = cleaned + ";"
        else:
            del el["style"]
    return str(frag)


def _extract_decls(style):
    """Yield (prop, full-declaration) pairs from an inline style string."""
    for chunk in style.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        prop = chunk.split(":", 1)[0].strip()
        yield prop, chunk


def _text_of(el):
    return el.get_text(" ", strip=True) if isinstance(el, Tag) else ""


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


# ── shared: a rich atom's verbatim fidelity facts (rule 26 verbatim-default) ──
# A slide / tab-panel is richer than a logo (media + link + text). Instead of
# lifting each text/media field (which is fidelity-unsafe on JS-composed markup),
# the atom carries its VERBATIM cleaned source markup as `orig` — rendered as-is
# by the view (byte-exact by construction). The atom stays COMPOSABLE (a real
# child node the editor can add/remove/reorder) while being fidelity-safe: the
# first media + first link surface as editable slots (rule 26/27), the rest of
# the markup is the verbatim default. This is the logo `imgOrig` contract applied
# to any repeated widget item.

def _clean_state_class(markup, is_slide):
    """Drop transient JS state tokens (active/next/prev/cloned/…) from the ROOT
    element's class of a slide/panel fragment, so a persisted node never freezes
    one carousel frame as 'active'. Only the outer element is touched (inner
    source classes are design and stay verbatim). Returns cleaned markup."""
    if not is_slide:
        return markup
    from bs4 import BeautifulSoup
    frag = BeautifulSoup(markup, "html.parser")
    root = next((c for c in frag.children if isinstance(c, Tag)), None)
    if root is not None and root.get("class"):
        kept = [c for c in _classes(root)
                if c not in SLIDE_STATE_TOKENS
                and not any(sub in c for sub in CLONE_CLASS_SUBSTR)]
        if kept:
            root["class"] = kept
        else:
            del root["class"]
    return str(frag)


def _rich_atom_facts(el, variant):
    """Fidelity facts of one slide / tab-panel / accordion-item element.
    `orig` = the element's cleaned inner+outer markup (JS-state stripped) rendered
    verbatim; first <img> + first <a href> surface as the editable image + link."""
    cleaned = _clean_state_class(_strip_js_state(str(el)), variant == "slide")
    img = el.find("img")
    src = ""
    alt = ""
    if img is not None:
        src = (img.get("src") or img.get("data-src") or "").strip()
        if src.startswith("data:"):
            src = ""
        alt = img.get("alt", "") or ""
    a = el.find("a", href=True)
    href = (a.get("href").strip() if a is not None else "")
    return {
        "variant": variant,
        "orig": cleaned,                 # verbatim cleaned markup (fidelity default)
        "elClass": " ".join(_classes(el)),
        "src": src,                       # first image -> editable weakref slot
        "alt": alt,
        "title": "",                      # optional label (tabs set this)
        "href": href,                     # first link -> editable j:linkType slot
        "text": _text_of(el)[:200],       # short preview (never persisted content)
        "breakClass": "",
    }


# ── recognizer: CAROUSEL / SLIDER (JS-Island, cloned-slide dedup) — P6.3-bis ──

# state/clone class tokens a JS carousel toggles on slides (active/prev/next/…) or
# injects on clones. These fragment the raw class signature, so a slide-track's
# sibling run looks heterogeneous unless we NORMALIZE them away before grouping —
# that normalization is exactly what lets `asr-slide-item active`,
# `asr-slide-item cloned prev`, `asr-slide-item next` all count as ONE slide type.
SLIDE_STATE_TOKENS = (CLONE_CLASS_TOKENS | {
    "active", "prev", "next", "current", "is-active", "is-current",
    "swiper-slide-active", "swiper-slide-next", "swiper-slide-prev",
    "slick-active", "slick-current", "slick-center", "owl-item",
    "selected", "focused", "visible", "hidden",
})

# a "slide" is a BLOCK element; list-semantics children (<li>/<option>/<dd>) are a
# TEXT RUN, never carousel slides (rule 24). A carousel view/track never nests a
# real slide inside an <ul>/<ol> item run.
_NON_SLIDE_TAGS = {"li", "option", "dd", "dt", "th", "td", "tr", "optgroup"}


def _slide_sig(el):
    """Class signature with clone/state tokens removed — so state variants of the
    same slide group together (the key fix for de-cloning a JS slider track)."""
    cls = [c for c in _classes(el)
           if c not in SLIDE_STATE_TOKENS
           and not any(sub in c for sub in CLONE_CLASS_SUBSTR)]
    return (el.name, tuple(sorted(cls)))


def _find_slide_track(root):
    """Find the wrapper whose direct children are a run of same-(normalized)-
    signature SLIDE siblings (>=MIN_SLIDES canonical after de-cloning), each a
    BLOCK element that DIRECTLY wraps media (a real slide, not a text list).
    Returns (track, [canonical_slides], [all_slides]) or (None, None, None).

    Chooses the track with the MOST canonical slides (the real slide row dominates
    a page's nested repeaters — a deeper 2-cell grid inside one slide loses to the
    N-slide row); ties break by document order. Structural + agnostic: keyed on
    normalized class signature + direct-media-wrap, never a project slide class.
    Clones are de-duplicated so the infinite-scroll illusion never inflates the
    child count (P6.3-bis core)."""
    best_track = None
    best_canon = None
    best_all = None
    for node in [root] + root.find_all(True):
        kids = _child_tags(node)
        if len(kids) < MIN_SLIDES:
            continue
        # group by NORMALIZED signature (state/clone tokens removed)
        sig_counts = {}
        for k in kids:
            if k.name in _NON_SLIDE_TAGS:
                continue
            sig_counts.setdefault(_slide_sig(k), []).append(k)
        if not sig_counts:
            continue
        sig, run = max(sig_counts.items(), key=lambda kv: len(kv[1]))
        # the run must dominate the track's children (a slider track is uniform:
        # N slides + maybe nav arrows/indicators; heterogeneous wrappers refused)
        if len(run) < MIN_SLIDES or len(run) < 0.6 * len(kids):
            continue
        # each slide must DIRECTLY carry media (a content slide, not a text run).
        # Direct = media somewhere in the slide subtree, but the slide itself is a
        # block wrapper — the _NON_SLIDE_TAGS guard already excluded <li> runs.
        if not all(_wraps_media(s) for s in run):
            continue
        canonical = _dedup_clones(run)
        if len(canonical) < MIN_SLIDES:
            continue
        if best_canon is None or len(canonical) > len(best_canon):
            best_track, best_canon, best_all = node, canonical, run
    if best_track is None:
        return None, None, None
    return best_track, best_canon, best_all


def _recognize_carousel(root, ns):
    """A JS carousel/slider (swiper/slick/owl/AEM cmp-carousel or the custom
    asr-content-slider) -> ns:carousel of typed slide atoms (ns:card variants).

    FIDELITY-FIRST + COMPOSABLE:
      - CLONED slides (infinite-scroll illusion) are de-duplicated so only the
        CANONICAL slides become child nodes (P6.3-bis core — no duplicated content).
      - JS SCROLL STATE (inline transform/translate/opacity/display/width) is
        stripped from every slide so a node never freezes one scroll frame.
      - Each canonical slide carries its VERBATIM cleaned markup (`orig`, rule 26)
        -> byte-exact by construction; first image + link are editable slots.
      - The carousel view (a JS Island) re-hydrates swipe/autoplay on the child
        nodes in LIVE; in EDIT each slide is an independent Page-Builder edit frame
        (G6b). So an unedited carousel renders identically, but is now composable.

    Refuses (returns None -> skeleton fallback) when the track is heterogeneous or
    has <2 canonical slides (a single-slide 'carousel' is just a banner — the
    existing banner path handles it)."""
    track, canonical, allslides = _find_slide_track(root)
    if track is None:
        return None
    # _find_slide_track already picks the track with the MOST canonical slides, so
    # a slide's inner 2-cell grid never wins over the N-slide row. A slide legitimately
    # containing an inner grid is fine — it rides the slide's verbatim `orig` markup.

    slides = []
    for s in canonical:
        facts = _rich_atom_facts(s, "slide")
        slides.append(facts)
    if len(slides) < MIN_SLIDES:
        return None

    src_classes = _source_class_chain(root, track)
    n_clones = len(allslides) - len(canonical)
    return {
        "kind": "carousel",
        "nodeType": f"{ns}:carousel",
        "atomType": f"{ns}:card",
        "container": {
            "sourceClasses": src_classes,
            "rootClass": " ".join(_classes(root)),
            "trackClass": " ".join(_classes(track)),
            "heading": "",
            "clonesRemoved": n_clones,
            "slideCount": len(slides),
        },
        "master": None,
        "children": slides,
        "editableLinks": sum(1 for s in slides if s["href"]),
        "editableImages": sum(1 for s in slides if s["src"]),
    }


# ── recognizer: TABS / ACCORDION (JS show/hide) — P6.3-bis ────────────────────

def _tab_labels_and_panels(root):
    """Locate the tab labels + panels of a JS tabs widget.
    Returns ([label_text,...], [panel_el,...]) or (None, None).

    Supports the two dominant patterns generically:
      - ARIA: role="tablist" > role="tab" labels + role="tabpanel" panels;
      - BEM (AEM cmp-tabs / bootstrap-ish): `.cmp-tabs__tab` / `*__tab` labels
        + `.cmp-tabs__tabpanel` / `*__tabpanel` / `*__panel` panels.
    Panels must be >=2 and label count must match panel count (a tabs widget is a
    1:1 label↔panel map). The active/first panel is the default (view sets idx 0)."""
    def _by_role(role):
        return [e for e in root.find_all(attrs={"role": role})]

    tabs = _by_role("tab")
    panels = _by_role("tabpanel")
    if not tabs or not panels:
        # BEM fallback: class tokens ending __tab / __tabpanel|__panel
        def _bem(sub):
            return [e for e in root.find_all(True)
                    if any(c.endswith(sub) for c in _classes(e))]
        tabs = tabs or _bem("__tab")
        panels = panels or (_bem("__tabpanel") or _bem("__panel"))
    if len(panels) < 2:
        return None, None
    # a tabpanel nested in another tabpanel is not a top-level tab (AEM carousels
    # expose role=tabpanel on their slides — exclude panels that live inside a
    # slide/another panel to avoid grabbing a carousel as tabs).
    panels = [p for p in panels
              if not any(op is not p and op in p.parents for op in panels)]
    if len(panels) < 2:
        return None, None
    labels = [_text_of(t) for t in tabs] if tabs else []
    # align labels to panels; if counts differ, fall back to positional label text
    if len(labels) != len(panels):
        labels = (labels + [""] * len(panels))[:len(panels)]
    return labels, panels


def _recognize_tabs(root, ns):
    """A JS tabs widget (ARIA tablist or AEM cmp-tabs) -> ns:tabs of ns:tab panes.

    FIDELITY-FIRST + COMPOSABLE: each panel becomes a ns:tab child carrying its
    VERBATIM cleaned markup (`orig`, rule 26) + the tab LABEL as its title; the
    tabs view (Island) shows/hides panels in LIVE (first active) and stacks them
    as edit frames in EDIT (G6b). An unedited tabs block renders identically.

    Refuses when there is no clean 1:1 label↔panel tab structure (skeleton
    fallback). The AEM carousel's role=tabpanel slides are excluded by the
    nested-panel guard so a carousel is never mis-read as tabs (carousel wins in
    the registry order anyway)."""
    labels, panels = _tab_labels_and_panels(root)
    if panels is None:
        return None
    tabs = []
    for i, p in enumerate(panels):
        facts = _rich_atom_facts(p, "tab")
        facts["title"] = (labels[i] if i < len(labels) else "") or f"Tab {i + 1}"
        facts["active"] = (i == 0)
        tabs.append(facts)

    # the widget root class chain (skin = source classes)
    # find the common wrapper of the panels for the source-class record
    wrapper = panels[0].parent or root
    src_classes = _source_class_chain(root, wrapper)
    return {
        "kind": "tabs",
        "nodeType": f"{ns}:tabs",
        "atomType": f"{ns}:tab",
        "container": {
            "sourceClasses": src_classes,
            "rootClass": " ".join(_classes(root)),
            "wrapperClass": " ".join(_classes(wrapper)),
            "heading": "",
            "tabCount": len(tabs),
        },
        "master": None,
        "children": tabs,
        "editableLinks": sum(1 for t in tabs if t["href"]),
        "editableImages": sum(1 for t in tabs if t["src"]),
    }


# ── recognizer registry (ordered; first faithful match wins) ─────────────────
# Order matters: carousel BEFORE tabs (an AEM carousel exposes role=tabpanel on
# its slides; the carousel recognizer's slide-track structure matches first, and
# the tabs recognizer separately guards against nested panels). logoWall is the
# most specific (uniform <a><img> wall) so it stays first.

RECOGNIZERS = [
    _recognize_logowall,
    _recognize_carousel,
    _recognize_tabs,
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
    # carousel/tabs near-miss diagnostics first (the P6.3-bis library gaps)
    track, canonical, allslides = _find_slide_track(el)
    if track is not None:
        return (f"slide-track-but-refused (slides={len(allslides)}, "
                f"canonical={len(canonical)}, clones={len(allslides) - len(canonical)})")
    labels, panels = _tab_labels_and_panels(el)
    if panels is not None:
        return f"tabs-structure-but-refused (panels={len(panels)})"
    rep, anchors = _find_repeater(el)
    if rep is None:
        n_a = len(el.find_all("a", href=True))
        n_img = len(el.find_all(["img", "picture"]))
        n_panel = len(el.find_all(attrs={"role": "tabpanel"}))
        n_form = len(el.find_all(["form", "iframe"]))
        return (f"no-recognizable-widget (anchors={n_a}, media={n_img}, "
                f"panels={n_panel}, forms={n_form})")
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
                       (len(v) if isinstance(v, list) else (0 if v is None else 1)))
                   for k, v in plan.items()}
        print(json.dumps(summary, indent=2))
