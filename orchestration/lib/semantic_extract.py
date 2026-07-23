#!/usr/bin/env python3
"""semantic_extract.py — Deterministic component/template extraction (v2).

The missing deterministic layer between raw HTML and the LLM adjudication step.
Where the old `extract-blocks.py` emitted every matching block (256 for 10 pages,
heavy nesting duplication), this collapses the DOM to *component altitude* and
clusters by *editable data shape* — the dimension a CMS actually models.

Pipeline (all deterministic, byte-stable across runs):
  1. Parse each cached page (bs4/lxml).
  2. Detect component nodes:
       - SXA mode  : elements with class "component" (Sitecore SXA convention).
       - agnostic  : <section>/<article> + semantic-class <div> + structural regions.
     Layout scaffolding (row/col/container/grid/slider/spacing) is transparent.
  3. For each component: compute its POSITION (header/main/footer), its editable
     FIELD SHAPE (title/body/image/link/…), and whether it is a CONTAINER with a
     repeated child item.
  4. Aggregate instances across pages by role -> candidate components with
     frequency, page coverage, layout variants, empty-instance count.
  5. Flag CROSS-CUTTING roles (present on >=80% of pages, in header/footer/nav).
  6. Fingerprint each page by its <main> component-role sequence -> template
     clusters (pages with a very similar macro skeleton).

Output (a clean, small candidate set the LLM can adjudicate reproducibly):
  <project>/workflow-output/semantic-candidates.json
  <project>/workflow-output/semantic-templates.json

Usage:
  python3 orchestration/lib/semantic_extract.py <project> [--max-pages N]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

from bs4 import BeautifulSoup, Tag

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provenance  # noqa: E402  (stamps semantic-candidates/templates.json)


# ── Tag vocab ─────────────────────────────────────────────────────
REGION_TAGS = {"header", "footer", "nav", "main", "section", "article", "aside"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
RICHTEXT_TAGS = {"p", "ul", "ol", "table", "blockquote", "dl", "figure"}
MEDIA_TAGS = {"img", "picture", "video", "svg", "iframe"}

# Pure layout / scaffolding classes — transparent, never a component ROLE.
# Precise (regex) matching so semantic tokens like "top-bar", "header-navigation",
# "content-block", "key-figures", "left-img" survive.
LAYOUT_EXACT = {
    "component", "container", "container-fluid", "container-bp", "row", "grid",
    "grid-2", "grid-3", "grid-4", "inner", "wrapper", "content-wrapper",
    "no-gutters", "clearfix", "flex", "d-flex", "d-block", "d-none", "d-inline",
    "d-inline-block", "swiffy-slider", "slide", "clear", "sr-only", "visually-hidden",
    "background-img", "img-fluid", "w-100", "h-100", "mw-100", "mh-100",
}
LAYOUT_RE = re.compile(
    r"^("
    r"col(-.*)?|offset-.*|order-.*|"
    r"(m|p)(t|b|s|e|x|y|l|r)?-(auto|\d.*)|"
    r"g(x|y)?-\d.*|gap-.*|"
    r"(w|h|vw|vh|mw|mh|minvh|maxvh|min-vh|max-vh)-\d.*|"
    r"bg-.*|"
    r"text-(center|left|right|start|end|white|dark|muted|primary|secondary|nowrap|uppercase|lowercase|capitalize)|"
    r"(justify|align)-.*|flex-.*|"
    r"(fw|fs|lh)-.*|rounded.*|shadow.*|border.*|position-.*|overflow-.*|z-\d.*|"
    r"d-(sm|md|lg|xl|xxl)-.*|"
    r"animated.*|height\d.*|basic-vertical.*|slider-.*|slide-.*|"
    r"pt-\d.*|pb-\d.*|ps-\d.*|pe-\d.*|px-\d.*|py-\d.*|"
    # framework/theme layout wrappers (Drupal Site Studio / Cohesion, Splide, etc.)
    r"selected-.*|selected--.*|coh-.*|ssa-.*|ssa-component.*|site-studio|splide.*|"
    # Tailwind responsive grid utilities (Next.js sites: lg:col-span-8, lg:col-start-7).
    # NB: col(-.*)? above already covers col-span/start/end; row-span is the only new one.
    r"(sm|md|lg|xl|xxl|2xl):.*|row-span-.*|"
    r"swiper-.*|swiper|"
    # Liferay layout-engine + fragment structure classes. Scoped to the ACTUAL Liferay
    # namespaces (lfr-, portlet-, clay-* / c-clay*, atb-) — NOT a bare `c-.*`, which
    # would swallow the common BEMIT/ITCSS `c-` component prefix (c-hero, c-card).
    r"lfr-.*|portlet-.*|clay-.*|c-clay.*|atb-.*|fragment-.*|lfr-layout.*"
    r")$"
)

# CSS-modules class shape: <block>_<localName>__<hash> (double-underscore before the
# build hash). The hash carries no meaning to an editor; the localName does. Also
# collapses a repeated leading block stem (richTextUnified_richTextUnifiedBody → …Body).
_CSSMOD_HASH = re.compile(r"__[A-Za-z0-9].*$")


def _dedupe_stem(tok):
    """richTextUnified_richTextUnifiedBody → richTextUnifiedBody (drop the repeated
    leading block prefix a CSS-modules name concatenates)."""
    parts = [p for p in tok.split("_") if p]
    if len(parts) >= 2 and parts[1].lower().startswith(parts[0].lower()):
        return "_".join(parts[1:])
    return tok


def clean_token(tok):
    """Strip CSS-module build hashes and redundant block prefixes from a class token
    so it can serve as a human-facing role. Non-CSS-module tokens pass through."""
    if not tok:
        return tok
    if "__" in tok:
        stripped = _CSSMOD_HASH.sub("", tok)
        if stripped:
            return _dedupe_stem(stripped)
    return tok


def classes_of(el):
    c = el.get("class")
    if not c:
        return []
    if isinstance(c, str):
        return c.split()
    return list(c)


def is_layout_class(tok):
    t = tok.lower()
    if t in LAYOUT_EXACT:
        return True
    return bool(LAYOUT_RE.match(t))


# ── Role derivation ───────────────────────────────────────────────

CHROME_TAGS = {"header", "footer", "nav"}


def _region_from_classes(cls):
    """Map CMS 'region' wrapper classes to a chrome position (Drupal, etc.)."""
    s = " ".join(cls).lower()
    for kw in ("header", "footer", "nav"):
        if f"region-{kw}" in s or f"region_{kw}" in s or f"{kw}-region" in s:
            return kw
    return None


def role_and_variants(el, sxa_mode):
    """Return (role, [semantic variant tokens]) for a component element.

    Structural chrome tags (header/footer/nav) and CMS region wrappers take their
    IDENTITY from the tag/region, not from a class token — so the same logical
    header unifies across SXA, WordPress and Drupal. Everything else uses the
    first non-layout class token as its role.
    """
    cls = classes_of(el)
    # clean CSS-module hashes first, THEN drop layout classes (a hashed token like
    # call_to_action_card__9Pqm4 must be de-hashed before the layout test sees it).
    semantic = [clean_token(c) for c in cls]
    semantic = [c for c in semantic if not is_layout_class(c)]
    if el.name in CHROME_TAGS:
        return el.name, semantic
    region = _region_from_classes(cls)
    if region:
        return region, [c for c in semantic if c not in (region, "region")]
    if el.name in REGION_TAGS and not semantic:
        return el.name, []
    if not semantic:
        # SXA splitter/layout component with no type token, or a bare wrapper.
        if "component" in cls:
            return "generic-container", []
        return el.name, []
    return semantic[0], semantic[1:]


# ── Component-node detection ──────────────────────────────────────

BLOCK_TAGS = {"div", "section", "article", "aside", "form", "ul", "ol", "header",
              "footer", "nav"}


def _content_signal(el):
    """Does this element carry contributor content (heading/media/link/text)?"""
    if _heading_descendants(el):
        return True
    if el.find(["img", "picture", "video", "iframe"]):
        return True
    if len(el.find_all("a", href=True)) >= 1:
        return True
    txt = el.get_text(" ", strip=True)
    return len(txt) > 40


def _is_block(el):
    return isinstance(el, Tag) and el.name in BLOCK_TAGS and _content_signal(el)


def _homogeneous(children):
    """>=3 siblings sharing tag + a common class token = a repeated item row."""
    if len(children) < 3:
        return False
    sig = Counter((c.name, tuple(sorted(t for t in classes_of(c) if not is_layout_class(t)))[:1])
                  for c in children)
    top, n = sig.most_common(1)[0]
    return n >= 3 and n >= 0.6 * len(children)


# A heading is NOT only <h1>-<h6>. Design-system / CSS-in-JS sites (Next.js,
# styled-components, Contentful) render visual headings as <p>/<span>/<div> with a
# typography class (`typography_heading__…`, `sectionTitle`, `headline-lg`) and/or
# ARIA (role="heading" / aria-level). Missing these made the altitude finder
# over-decompose titled promo bands (e.g. contentful's Palmata card), orphaning the
# title + CTA. `heading|headline` only (NOT bare `title`, which hits job-title/
# card-subtitle inside items and would over-merge).
HEADING_CLASS_RE = re.compile(r"(?:^|[-_ ])(heading|headline)(?:$|[-_ 0-9])", re.I)


def _is_heading(el):
    if not isinstance(el, Tag):
        return False
    if el.name in HEADING_TAGS:
        return True
    if el.get("role") == "heading" or el.get("aria-level"):
        return True
    if el.name in ("p", "span", "div") and HEADING_CLASS_RE.search(" ".join(classes_of(el))):
        return True
    return False


def _heading_descendants(node):
    """All heading-like descendants (semantic hN + ARIA + typography-heading class)."""
    hs = list(node.find_all(list(HEADING_TAGS)))
    hs += node.find_all(attrs={"role": "heading"})
    hs += node.find_all(attrs={"aria-level": True})
    hs += [e for e in node.find_all(["p", "span", "div"], class_=True)
           if HEADING_CLASS_RE.search(" ".join(classes_of(e)))]
    return hs


def _own_heading(node):
    """True if node carries its OWN heading (a section title/intro) that is not
    inside one of its item blocks — i.e. node is a 'titled section', not a pure
    layout wrapper. Such a node IS the component (title + intro + items as children)."""
    block_kids = [c for c in node.children if isinstance(c, Tag) and _is_block(c)]
    for h in _heading_descendants(node):
        if h.get_text(strip=True) and not any(bk in h.parents for bk in block_kids):
            return True
    return False


# A wrapper carrying a VISIBLE background (a distinct colour or an image) is a
# banner / hero / coloured section — one component that OWNS that background, not a
# transparent layout wrapper to descend through. Missing this split the hero's inner
# text off from its coloured wrapper, so the reconstruction never painted the band
# (the "bg-on-wrapper" pixel gap on contentful careers/case-studies). Detected from
# STATIC html only (inline style + hero/banner class) so the model and the fidelity
# probe agree — no computed styles.
_BG_CLASS_RE = re.compile(r"(?:^|[-_ ])(hero|banner|masthead|jumbotron|full[-_]?size|promo|cta)(?:$|[-_ ])", re.I)
_BG_VAL_SKIP = re.compile(r"^(transparent|none|inherit|initial|unset|currentcolor|#fff(fff)?\b|white|rgba?\(\s*255\s*,\s*255\s*,\s*255|rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0)", re.I)


def _has_visual_bg(node):
    """True if node carries its OWN visible background (distinct colour / image)."""
    style = (node.get("style") or "").lower()
    if "background" in style:
        m = re.search(r"background(?:-color|-image|)\s*:\s*([^;]+)", style)
        if m:
            val = m.group(1).strip()
            if val and not _BG_VAL_SKIP.match(val):
                return True
    return bool(_BG_CLASS_RE.search(" ".join(classes_of(node))))


def _find_component_row(node, depth=0):
    """Recursively locate the 'component altitude' below a content region:
    descend transparent single-block wrappers; at the first level with >=2 block
    children, emit those children (a heterogeneous zone) — unless they are a
    homogeneous repeated row, in which case emit the parent as one container.

    A node that carries its OWN title/intro (heading not inside an item block) OR its
    OWN visible background (a hero/banner/coloured section) is emitted whole (Option A)
    — so section headings/intros and coloured band backgrounds are never dropped
    above the component row."""
    if depth > 7:
        return [node]
    block_children = [c for c in node.children if _is_block(c)]
    if len(block_children) == 0:
        return [node]
    # titled section OR background-bearing band: keep the whole node. depth>0 so we
    # never swallow the top-level content region itself.
    if depth > 0 and (_own_heading(node) or _has_visual_bg(node)):
        return [node]
    if len(block_children) == 1:
        # transparent wrapper (region/article/site-studio chain) — descend
        return _find_component_row(block_children[0], depth + 1)
    if _homogeneous(block_children):
        return [node]                      # listing/grid: node is the container
    out = []
    for c in block_children:               # heterogeneous zone: recurse per block
        out.extend(_find_component_row(c, depth + 1))
    return out


def _agnostic_component_nodes(soup):
    """Component nodes for a non-SXA site: chrome regions + the main-content
    component row(s). Avoids the deep-BEM explosion by stopping at altitude."""
    body = soup.body or soup
    nodes, seen = [], set()

    def add(el):
        if isinstance(el, Tag) and id(el) not in seen:
            seen.add(id(el))
            nodes.append(el)

    # chrome: header/footer/nav tags + region--header/footer/nav wrappers
    for tag in body.find_all(list(CHROME_TAGS)):
        add(tag)
    for div in body.find_all("div"):
        if _region_from_classes(classes_of(div)):
            add(div)

    # main content anchors
    anchors = list(body.find_all("main"))
    if not anchors:
        for div in body.find_all("div"):
            cl = " ".join(classes_of(div)).lower()
            if "region--content" in cl or "region-content" in cl or "main-content" in cl:
                anchors.append(div)
    if not anchors:
        anchors = [body]

    for anc in anchors:
        rows = _find_component_row(anc)
        # The anchor must never swallow the page (2026-07-23, singpost rebuild):
        # a Tailwind main whose bands are all <section> siblings carries ONLY
        # layout classes, so _homogeneous sees N x ('section', ()) and returns
        # [main] as "one container" - which the anchor-skip below then drops,
        # leaving ZERO main-content components site-wide (1576 instances fell
        # to rawHtml and were dropped as empty). Descend one level instead so
        # each band resolves at its own altitude.
        if rows == [anc]:
            rows = []
            for c in (x for x in anc.children if _is_block(x)):
                rows.extend(_find_component_row(c, 1))
        for comp in rows:
            # don't re-emit a chrome region already captured, and skip the anchor
            if comp is anc or comp.name in CHROME_TAGS:
                continue
            add(comp)
    return nodes


def build_component_index(soup, sxa_mode):
    """Return the ordered list of Tag elements that are 'component nodes'."""
    if sxa_mode:
        return [el for el in soup.find_all(True)
                if isinstance(el, Tag) and "component" in classes_of(el)]
    return _agnostic_component_nodes(soup)


SEMANTIC_KEYWORDS = (
    "hero", "banner", "slider", "carousel", "gallery", "listing", "cards",
    "card", "push", "teaser", "widget", "feature", "testimonial", "faq",
    "accordion", "tabs", "cta", "call-to-action", "pricing", "team", "portfolio",
    "footer", "header", "nav", "breadcrumb", "newsletter", "search", "map",
    "content-block", "editorial", "quicklink", "key-figure", "promo", "highlight",
    "block", "module", "section", "region",
)


def _has_semantic_class(cls):
    s = " ".join(cls).lower()
    return any(k in s for k in SEMANTIC_KEYWORDS)


def _bounded_descendants(el, maxdepth):
    stack = [(c, 1) for c in el.children if isinstance(c, Tag)]
    while stack:
        node, d = stack.pop()
        yield node
        if d < maxdepth:
            stack.extend((c, d + 1) for c in node.children if isinstance(c, Tag))


def _div_has_content_mixing(el, maxdepth=2):
    """Agnostic component signal (no class vocabulary): a class-less <div> that
    leads with a heading and carries body/media/link content is a content block —
    catches components on hand-coded / non-SXA sites the keyword list misses."""
    has_heading = has_content = False
    for n in _bounded_descendants(el, maxdepth):
        if _is_heading(n):
            has_heading = True
        elif n.name in ("img", "picture", "video", "a", "p", "ul", "ol"):
            has_content = True
        if has_heading and has_content:
            return True
    return False


def nearest_region(el):
    # chrome tags self-classify (a <header> has no header ancestor)
    if el.name in ("header", "footer", "nav", "main"):
        return el.name
    r = _region_from_classes(classes_of(el))
    if r:
        return r
    for anc in el.parents:
        if isinstance(anc, Tag):
            if anc.name in ("header", "footer", "nav", "main"):
                return anc.name
            ar = _region_from_classes(classes_of(anc))
            if ar:
                return ar
    return "main"


# ── Field / data-shape extraction ─────────────────────────────────

# DOM signals that a component needs client-side behaviour (a Jahia Island),
# beyond a plain server-rendered view. Class tokens complement the tags for
# JS-driven widgets built from bare divs (carousel, tabs, filter bars…).
INTERACTIVE_TAGS = {"form", "input", "select", "textarea", "button",
                    "video", "canvas", "details", "dialog"}
INTERACTIVE_CLASS_RE = re.compile(
    r"carousel|slider|swiper|tabs|accordion|search|filter|toggle|dropdown"
    r"|modal|popin|player|lightbox", re.I)


def extract_fields(comp_el, comp_set):
    """Walk comp_el's subtree, stopping at nested component nodes, and build the
    editable field shape a contributor would set."""
    acc = {
        "headings": [], "images": [], "links": [],
        "text_parts": [], "has_richtext": False,
        "child_components": [],
        # bridge extras (content-load + Islands hint) — additive, never feed
        # shape_from_fields, so candidate shapes stay byte-stable vs pre-bridge
        "image_details": [], "link_details": [], "interactive": False,
    }

    def walk(node):
        for child in node.children:
            if not isinstance(child, Tag):
                txt = str(child).strip()
                if txt:
                    acc["text_parts"].append(txt)
                continue
            if child.name in ("script", "style", "noscript"):
                continue  # code, not contributor content (bytes stay in blobs)
            if child in comp_set:
                acc["child_components"].append(child)
                continue  # do not descend into a nested component
            name = child.name
            if name in HEADING_TAGS:
                t = child.get_text(" ", strip=True)
                if t:
                    acc["headings"].append((name, t))
            if name in ("img", "picture"):
                src = child.get("src") or child.get("data-src") or child.get("data-lazy-src") or ""
                if src and not src.startswith("data:"):
                    acc["images"].append(src)
                    acc["image_details"].append(
                        {"src": src, "alt": child.get("alt", "") or ""})
            if name in ("video", "iframe"):
                acc["images"].append(child.get("src") or "media")
                acc["interactive"] = True
            if name == "a":
                href = child.get("href", "")
                if href and not href.startswith("#") and not href.startswith("javascript:"):
                    acc["links"].append(href)
                    acc["link_details"].append(
                        {"href": href, "text": child.get_text(" ", strip=True)[:120]})
            if name == "button":
                acc["links"].append("button")
            if name in INTERACTIVE_TAGS:
                acc["interactive"] = True
            if name in RICHTEXT_TAGS:
                acc["has_richtext"] = True
            walk(child)

    walk(comp_el)
    return acc


def shape_from_fields(acc):
    """Canonical editable field shape (list of 'role:type')."""
    shape = []
    if acc["headings"]:
        shape.append("title:string")
    # rich body vs plain text
    text_len = len(" ".join(acc["text_parts"]))
    if acc["has_richtext"] and text_len > 40:
        shape.append("body:richtext")
    elif text_len > 20:
        shape.append("text:string")
    if acc["images"]:
        shape.append("image:weakref" if len(acc["images"]) == 1 else "images:weakref[]")
    if acc["links"]:
        shape.append("link:linkType" if len(acc["links"]) == 1 else "links:linkType[]")
    return sorted(shape)


def detect_repeated_child(comp_el, comp_set):
    """If the component has no nested component children but contains a repeated
    sibling structure (>=3 same tag+class), treat it as a container of items.
    Returns (is_container, child_shape, item_outer_html) or (False, None, None)."""
    best = None
    for node in comp_el.find_all(True):
        if node in comp_set and node is not comp_el:
            continue
        kids = [c for c in node.children if isinstance(c, Tag)]
        if len(kids) < 3:
            continue
        sig = Counter((k.name, " ".join(sorted(classes_of(k)))) for k in kids)
        (top_sig, cnt) = sig.most_common(1)[0]
        if cnt >= 3:
            best = [k for k in kids if (k.name, " ".join(sorted(classes_of(k)))) == top_sig]
            break
    if not best:
        return False, None, None
    item_acc = extract_fields(best[0], comp_set)
    return True, shape_from_fields(item_acc), str(best[0])


# ── Contribution lift (QUALITY-PLAN P2.5, workstreams A+B) ────────
# DOM-level field extraction: markers replace element CONTENT in the tree, so
# substitution can never miss (the P2 string-unique-match produced 59/62 dead
# `text` props). decompose_group() self-checks: recompose(skeleton, fields,
# children) must equal the group's original serialization BYTE-FOR-BYTE, or the
# caller falls back to verbatim rawHtml — a broken skeleton never ships.

TEXT_BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "blockquote",
              "pre", "table", "hr"}
# elements a richtext body must never swallow (script-driven / form widgets)
NEVER_IN_BODY = {"form", "script", "style", "iframe", "select", "input",
                 "textarea", "video", "button"}
# block-level names that disqualify a div/span/a from being a pseudo-paragraph
_BLOCKY = {"div", "section", "article", "aside", "header", "footer", "nav",
           "ul", "ol", "li", "table", "form", "p", "blockquote", "pre",
           "h1", "h2", "h3", "h4", "h5", "h6", "figure", "main",
           "iframe", "video", "select", "input", "textarea", "script", "style"}
FIELD_MARK = "{{f:%s}}"
CHILD_MARK = "{{child:%d}}"


def _esc_text(v):
    """bs4-minimal escaping (&, <, > — quotes stay raw). The TS view MUST use
    the same rule or recomposition diverges from the certified bytes."""
    import html as _h
    return _h.escape(v, quote=False)


def ban_subtree(banned_ids, el):
    banned_ids.add(id(el))
    if isinstance(el, Tag):
        for d in el.descendants:
            banned_ids.add(id(d))


def lift_title(scope, banned_ids):
    """First heading whose subtree carries EXACTLY ONE non-whitespace text node
    (pure-text headings AND span/strong-wrapped ones — the inline wrappers stay
    in the skeleton, the marker replaces the text node; P2.5-C1). Returns the
    clean value or None. The byte-identity self-check remains the safety net."""
    from bs4 import NavigableString
    for d in scope.find_all(sorted(HEADING_TAGS)):
        if id(d) in banned_ids:
            continue
        texts = [t for t in d.find_all(string=True) if str(t).strip()]
        if len(texts) != 1:
            continue
        raw = str(texts[0])
        core = raw.strip()
        if len(core) < 2 or "{{" in core:
            continue
        lead = raw[:len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
        texts[0].replace_with(NavigableString(lead + FIELD_MARK % "title" + trail))
        ban_subtree(banned_ids, d)  # marked — never part of a body run
        return core
    return None


def _esc_attr(v):
    """bs4-minimal attribute escaping (&, <, >, \") — the recomposition rule
    for values spliced into attribute positions ({{link:href}})."""
    return (v.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def lift_media(scope, banned_ids, cap=16):
    """P2.5-C2: media units in the skeleton residue (whole <picture> elements
    and standalone <img>) -> {{media:imageN}} markers. Returns (media, total):
    media = [{name, orig, src, alt}] for the first `cap` units (orig = exact
    original markup — the view's byte-exact default render); total = all units
    seen (the probe reports over-cap leftovers, never silently)."""
    from bs4 import NavigableString
    units = []
    for el in scope.find_all(["picture", "img"]):
        if id(el) in banned_ids:
            continue
        if el.name == "img" and any(isinstance(a, Tag) and a.name == "picture"
                                    for a in el.parents):
            continue
        img = el if el.name == "img" else el.find("img")
        src = (img.get("src") if img else "") or ""
        if not src or src.startswith("data:") or "{{" in src:
            continue
        # ICONS ARE DESIGN FURNITURE, NOT CONTRIBUTED MEDIA (2026-07-20,
        # delivery-rates: a 24px download icon lifted as a media unit lost its
        # sizing wrapper when folded into body and rendered ~1000px tall).
        # svg + icon-named images stay INLINE in the markup, keeping the
        # wrapper classes that size them; the DAM slot is for real imagery.
        alt_cls = ((img.get("alt") or "") + " "
                   + " ".join(img.get("class") or [])).lower()
        if src.lower().split("?")[0].endswith(".svg") or "icon" in alt_cls:
            continue
        units.append((el, img, src))
    media = []
    for el, img, src in units[:cap]:
        name = "image" if not media else f"image{len(media) + 1}"
        media.append({"name": name, "orig": str(el), "src": src,
                      "alt": (img.get("alt") if img else "") or ""})
        ban_subtree(banned_ids, el)
        el.replace_with(NavigableString("{{media:%s}}" % name))
    return media, len(units)


def lift_link(scope, banned_ids, fields):
    """P2.5-C3: the FIRST residue <a href> becomes the payload's contributor
    link (j:linkType is a node-level singleton). href value -> {{link:href}};
    a single-text-node label -> {{f:linkLabel}} in `fields`. Returns
    {href, label?} or None. Remaining anchors stay verbatim (counted)."""
    from bs4 import NavigableString
    total = 0
    link = None
    for a in scope.find_all("a", href=True):
        if id(a) in banned_ids:
            continue
        href = a["href"]
        if not href or href.startswith(("#", "javascript:")) or "{{" in href:
            continue
        total += 1
        if link is not None:
            continue
        link = {"href": href}
        texts = [t for t in a.find_all(string=True) if str(t).strip()]
        if len(texts) == 1:
            raw = str(texts[0])
            core = raw.strip()
            if len(core) >= 2 and "{{" not in core:
                lead = raw[:len(raw) - len(raw.lstrip())]
                trail = raw[len(raw.rstrip()):]
                texts[0].replace_with(NavigableString(
                    lead + FIELD_MARK % "linkLabel" + trail))
                fields["linkLabel"] = core
                link["label"] = core
        a["href"] = "{{link:href}}"
        ban_subtree(banned_ids, a)
    return link, total


def _run_eligible(el, banned_ids):
    """Run member: classic text block, image, figure, or an element whose
    subtree is purely inline (CTA link, name div) — all valid inside richtext."""
    if not isinstance(el, Tag) or id(el) in banned_ids:
        return False
    if any(id(d) in banned_ids for d in el.descendants):
        return False
    if el.name in NEVER_IN_BODY:
        return False
    if any(isinstance(d, Tag) and d.name in NEVER_IN_BODY for d in el.descendants):
        return False
    if el.name in TEXT_BLOCK or el.name in ("img", "picture", "figure"):
        return True
    if el.name in ("div", "span", "a", "strong", "em"):
        return not any(isinstance(d, Tag) and d.name in _BLOCKY
                       for d in el.descendants)
    return False


def _run_chars(pieces):
    return sum(len(p.get_text(" ", strip=True)) for p in pieces
               if isinstance(p, Tag))


def lift_bodies(scope, banned_ids, cap=18, min_chars=8):
    """ALL contiguous sibling runs of run-eligible elements (whitespace between
    members joins the run), document order, greedy non-overlapping. Each run
    becomes {{f:body}}/{{f:body2}}/…; returns {name: exact serialized HTML} —
    the richtext values. Pure-image runs (no text) stay inline for phase C."""
    from bs4 import NavigableString
    runs = []
    for node in [scope] + scope.find_all(True):
        if id(node) in banned_ids:
            continue
        kids = list(node.children)
        i = 0
        while i < len(kids):
            if not _run_eligible(kids[i], banned_ids):
                i += 1
                continue
            pieces = [kids[i]]
            k = i + 1
            while k < len(kids):
                nxt = kids[k]
                if isinstance(nxt, NavigableString) and not str(nxt).strip():
                    if k + 1 < len(kids) and _run_eligible(kids[k + 1], banned_ids):
                        pieces.extend([nxt, kids[k + 1]])
                        k += 2
                        continue
                    break
                if _run_eligible(nxt, banned_ids):
                    pieces.append(nxt)
                    k += 1
                    continue
                break
            if _run_chars(pieces) >= min_chars:
                runs.append(pieces)
                for p in pieces:
                    ban_subtree(banned_ids, p)  # later scans skip taken runs
            i = k
    if len(runs) > cap:  # keep the biggest `cap` runs, back in document order
        keep = sorted(sorted(range(len(runs)),
                             key=lambda r: -_run_chars(runs[r]))[:cap])
        runs = [runs[r] for r in keep]
    fields = {}
    for n, pieces in enumerate(runs):
        name = "body" if n == 0 else f"body{n + 1}"
        fields[name] = "".join(str(p) for p in pieces)
        pieces[0].replace_with(NavigableString(FIELD_MARK % name))
        for p in pieces[1:]:
            p.extract()
    return fields


_LABEL_PARENTS = {"a", "span", "strong", "em", "b", "label", "div", "li",
                  "td", "th", "figcaption", "small", "cite", "dt", "dd"}
_LABEL_SKIP_ANCESTORS = {"script", "style", "title", "noscript", "select",
                         "textarea", "option", "svg"}


def lift_labels(scope, banned_ids, cap=30, min_len=2, max_len=80):
    """Residual short text nodes -> PLAIN {{f:labelN}} single-line fields.

    lift_bodies refuses any subtree holding a NEVER_IN_BODY control - right for
    RICHTEXT (form controls inside a body prop would be mangled by the editor),
    but it leaves mega-menu property links, card-title divs and utility labels
    frozen in the skeleton (observed: 5.1K chars of property-name anchors on one
    page, poisoned by a single embedded search <input>). A plain TEXT prop has
    no such constraint: replace each text NODE with a marker (lead/trail
    whitespace preserved, exactly like lift_title) and store the stripped value.
    recompose's _esc_text substitution is byte-identical for bs4-serialized
    text; the group byte self-check remains the safety net. Longest-first cap,
    names in document order (label, label2, ...)."""
    from bs4 import NavigableString
    cands = []
    for tn in scope.find_all(string=True):
        if type(tn) is not NavigableString:      # Comment/CData/Doctype: never
            continue
        if id(tn) in banned_ids:
            continue
        par = tn.parent
        if par is None or par.name not in _LABEL_PARENTS:
            continue
        if any(p.name in _LABEL_SKIP_ANCESTORS for p in tn.parents):
            continue
        raw = str(tn)
        core = raw.strip()
        if not (min_len <= len(core) <= max_len) or "{{" in core:
            continue
        if not re.search(r"\w", core):           # bare separators ("|", "-")
            continue
        cands.append(tn)
    if len(cands) > cap:  # keep the longest `cap`, back in document order
        keep = sorted(sorted(range(len(cands)),
                             key=lambda i: -len(str(cands[i]).strip()))[:cap])
        cands = [cands[i] for i in keep]
    fields = {}
    for n, tn in enumerate(cands):
        raw = str(tn)
        core = raw.strip()
        name = "label" if n == 0 else f"label{n + 1}"
        lead = raw[:len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
        tn.replace_with(NavigableString(lead + FIELD_MARK % name + trail))
        fields[name] = core
    return fields


def find_repeated_items(group):
    """Outermost element whose children hold >=3 same-signature content-bearing
    Tags — those are the container's ITEMS (each becomes a child node)."""
    for node in [group] + group.find_all(True):
        kids = [c for c in node.children if isinstance(c, Tag)]
        if len(kids) < 3:
            continue
        sigs = [(k.name, " ".join(sorted(classes_of(k)))) for k in kids]
        top, n = Counter(sigs).most_common(1)[0]
        if n >= 3:
            if top[0] in TEXT_BLOCK:
                # repeated <p>/<h*>/<ul> = a text RUN (one richtext body),
                # never container items (observed live: a Next.js article's
                # typography_paragraph* <p>s became 10 near-empty item nodes)
                continue
            items = [k for k, s in zip(kids, sigs) if s == top]
            if all(_count_leaves(k) for k in items):
                return items
    return None


def decompose_group(group, allow_items=True, run_cap=18, min_chars=8,
                    lift_titles=True):
    """MUTATES `group`. Splits a promoted top group into an editable skeleton:
      - items (repeated same-signature children) -> child payloads, each with
        its own skeleton + lifted title/body* fields, replaced by {{child:i}}
      - group-level title + body runs -> {{f:...}} markers (item subtrees and
        already-marked elements are banned from group runs)
    lift_titles=False (anonymous rawHtml blocks, which carry no mix:title):
    headings are NOT lifted separately — being TEXT_BLOCKs they simply join
    the richtext body runs, still fully editable.
    Returns {ok, original, skeleton, fields, children}; ok=False means the
    byte-identity self-check failed and the caller MUST load `original` as
    verbatim rawHtml instead."""
    from bs4 import NavigableString
    original = str(group)
    items = (find_repeated_items(group) or []) if allow_items else []
    children = []

    def lift_scope(scope, banned, titles):
        f = {}
        t = lift_title(scope, banned) if titles else None
        if t:
            f["title"] = t
        f.update(lift_bodies(scope, banned, cap=run_cap, min_chars=min_chars))
        media, media_total = lift_media(scope, banned)
        link, link_total = lift_link(scope, banned, f)
        f.update(lift_labels(scope, banned))
        return {"fields": f, "media": media, "mediaTotal": media_total,
                "link": link, "linkTotal": link_total}

    for it in items:
        pl = lift_scope(it, set(), lift_titles)
        pl["el"] = it
        children.append(pl)
    banned_ids = set()
    for it in items:
        ban_subtree(banned_ids, it)
    top = lift_scope(group, banned_ids, lift_titles)
    for i, ch in enumerate(children):
        ch["skeleton"] = str(ch["el"])
        ch["el"].replace_with(NavigableString(CHILD_MARK % i))
        del ch["el"]
    skeleton = str(group)
    out = {"ok": None, "original": original, "skeleton": skeleton,
           "fields": top["fields"], "media": top["media"],
           "mediaTotal": top["mediaTotal"], "link": top["link"],
           "linkTotal": top["linkTotal"], "children": children}
    out["ok"] = recompose_group(skeleton, top["fields"], children,
                                media=top["media"], link=top["link"]) == original
    return out


def recompose_group(skeleton, fields, children, media=None, link=None):
    """Reference recomposition (the TS skeleton renderer implements the same
    rules): child markers -> child skeleton fully substituted; body* values
    splice RAW (richtext HTML); media markers -> the unit's exact original
    markup (the byte-exact DEFAULT state); {{link:href}} -> attribute-escaped
    original href; every other field minimal-escaped."""
    def subst(html, flds, med, lnk):
        for m in med or []:
            html = html.replace("{{media:%s}}" % m["name"], m["orig"])
        if lnk:
            html = html.replace("{{link:href}}", _esc_attr(lnk["href"]))
        for k, v in flds.items():
            html = html.replace(FIELD_MARK % k,
                                v if k.startswith("body") else _esc_text(v))
        return html
    out = skeleton
    for i, ch in enumerate(children):
        out = out.replace(CHILD_MARK % i,
                          subst(ch["skeleton"], ch.get("fields") or {},
                                ch.get("media"), ch.get("link")))
    return subst(out, fields, media, link)


# ── Main-region partition (passthrough layer, QUALITY-PLAN P1.2) ──
# The ≥99 % fidelity invariant requires that EVERY content region of <main> is
# either a detected component or an explicit raw-HTML passthrough — nothing
# dropped. The partition is total by construction: every child of <main> is
# routed to exactly one bucket (component | descend-into-wrapper | passthrough).

_LEAF_MEDIA = {"img", "picture", "video", "iframe", "svg"}
_CHROME_NAMES = {"header", "footer", "nav"}
# class/id tokens naming CHROME (nav/header/footer) or a TRANSIENT SCAFFOLD overlay
# (modal/dialog/loading/backdrop/cookie…) — for SPAs with NO landmark tags (discoverasr AEM:
# the nav is a deep <div class="navigation-cmp"> and the real content sits BESIDE ~15
# modal/overlay/loading divs, so main_content_root stopped at the modal-crowded shallow root).
# Skipping these lets it descend to the real content container; the skipped subtrees ride the
# VERBATIM page shell (page_shell captures every chain-sibling byte-for-byte → 0-DOM safe).
# Whole-token match; "menu"/"header"(alone) are NOT listed (dropdowns / section titles = content).
_CHROME_SCAFFOLD_CLASS = re.compile(
    r"(?:^|[-_ ])(navigation|navbar|masthead|sidebar|footer|modal|dialog|overlay|backdrop|"
    r"loading|spinner|popup|drawer|offcanvas|cookie|consent|toast|lightbox)(?:$|[-_ ])", re.I)


def _is_chrome_scaffold(el):
    """True if el is chrome or a transient scaffold overlay, by tag OR class/id — so
    main_content_root skips it when locating the content root (it rides the verbatim shell)."""
    if el.name in _CHROME_NAMES:
        return True
    blob = " ".join(el.get("class") or []) + " " + (el.get("id") or "")
    return bool(_CHROME_SCAFFOLD_CLASS.search(blob))


def _count_leaves(el):
    """Content leaves = non-empty text nodes + media tags (svg counted once,
    not its internals). The partition gate's accounting unit."""
    n = 0
    for d in el.descendants:
        in_svg = any(isinstance(a, Tag) and a.name == "svg" for a in d.parents)
        in_chrome = any(isinstance(a, Tag) and a.name in _CHROME_NAMES for a in d.parents)
        if in_svg or in_chrome:
            continue
        if isinstance(d, Tag):
            if d.name in _LEAF_MEDIA:
                n += 1
        elif str(d).strip():
            n += 1
    if isinstance(el, Tag) and el.name in _LEAF_MEDIA:
        n += 1
    return n


_NONCONTENT_TAGS = {"script", "noscript", "style", "template", "link", "meta"}


def main_content_root(main):
    """Descend from <main> (or <body>) through wrappers that carry ONE dominant content
    region — Drupal's region--content, and (added 2026-07-06) SPA page shells whose real
    content sits beside chrome/scaffolding. Partitioning at the top altitude yields ONE
    full-page monolith (the §2 'pixel-perfect but editorially useless' trap) OR, on a
    landmark-less SPA, stops at the modal/script-crowded body. The traversed chain is
    recorded so the page shell recomposes those wrappers (and their skipped siblings)
    around the main Area — VERBATIM, so 0-DOM holds. Returns (root, chain).

    Descent rules: ignore non-content tags (script/style/…), chrome + transient scaffold
    (nav/footer/modal/overlay…), and comment stray-text (GTM markers). Descend while a
    SINGLE content child remains, OR one child DOMINATES the content (>=80% of leaves) —
    the latter drills past tracking iframes, date-pickers and other small widgets that sit
    beside the page's real content container (discoverasr: body[page] > <div> > … > nav |
    content — the content div holds 1955 of ~2050 leaves, so we reach it; the nav and the
    ~15 modals ride the verbatim shell). Real visible stray text still stops the descent."""
    from bs4 import Comment
    # SPA gate (anti-overfit): the aggressive descent (scaffold-class exclusion + dominant
    # child) is applied ONLY when the page has NO <main>/role=main landmark — i.e. main IS
    # <body> (a landmark-less SPA shell, e.g. discoverasr AEM). Pages WITH a real <main>
    # (Drupal/Next/SXA/Liferay: 18-20/20) keep the original single-significant-child descent,
    # so the SSR stacks (which were already clean) do NOT regress.
    spa = (getattr(main, "name", None) == "body")
    chain = []
    node = main
    while True:
        if spa:
            tags = [c for c in node.children if isinstance(c, Tag)
                    and c.name not in _NONCONTENT_TAGS and not _is_chrome_scaffold(c)]
            content_tags = [c for c in tags if _count_leaves(c)]
            stray = any((not isinstance(c, Tag)) and (not isinstance(c, Comment))
                        and str(c).strip() for c in node.children)
            if not content_tags or stray:
                return node, chain
            dom = max(content_tags, key=_count_leaves)
            tot = sum(_count_leaves(c) for c in content_tags)
            if len(content_tags) == 1 or _count_leaves(dom) >= 0.8 * tot:
                chain.append(dom)
                node = dom
                continue
            return node, chain
        # SSR path (unchanged): descend while exactly ONE child carries content leaves.
        tags = [c for c in node.children if isinstance(c, Tag) and c.name not in _CHROME_NAMES]
        content_tags = [c for c in tags if _count_leaves(c)]
        stray_text = any(not isinstance(c, Tag) and str(c).strip() for c in node.children)
        if len(content_tags) == 1 and not stray_text:
            chain.append(content_tags[0])
            node = content_tags[0]
            continue
        return node, chain


def partition_main(soup, obj_set):
    """Document-ordered total partition of the page's main region into
    component regions and passthrough regions. Chrome subtrees are excluded
    (covered by cross-cutting components in absolute areas).
    Returns {"regions": [...], "leavesTotal": N}."""
    no_main = soup.find("main") is None
    root = soup.find("main") or soup.body
    if root is None:
        return {"regions": [], "leavesTotal": 0}
    root, _chain = main_content_root(root)
    if root in obj_set:
        n = _count_leaves(root)
        return {"regions": [{"kind": "component", "el": root, "topIndex": 0}],
                "leavesTotal": n,
                "topLevels": [{"html": str(root), "leaves": n, "el": root}]}
    has_comp_below = set()
    for el in obj_set:
        for anc in el.parents:
            if isinstance(anc, Tag):
                has_comp_below.add(id(anc))
    regions = []
    top_levels = []   # coarse alternative: one entry per direct child of root,
                      # WRAPPERS INTACT — descending into a component-bearing
                      # wrapper drops the wrapper element itself (its grid/flex
                      # classes!), which collapses layout when regions load
                      # individually. A fully-demoted top group loads as one
                      # verbatim blob instead (see extract_content).

    def rec(node, top_index):
        for child in node.children:
            if not isinstance(child, Tag):
                txt = str(child).strip()
                if txt:  # even 1-char separators are counted leaves (bytes contract)
                    regions.append({"kind": "passthroughText", "html": txt,
                                    "leaves": 1, "topIndex": top_index})
                continue
            if child.name in _CHROME_NAMES:
                continue  # chrome — cross-cutting components own it
            if child in obj_set:
                regions.append({"kind": "component", "el": child,
                                "topIndex": top_index})
            elif id(child) in has_comp_below:
                rec(child, top_index)
            else:
                leaves = _count_leaves(child)
                if leaves:  # spacers / empty scaffolding carry no content
                    regions.append({"kind": "passthrough", "html": str(child),
                                    "leaves": leaves, "topIndex": top_index})

    ti = 0
    for child in root.children:
        if isinstance(child, Tag) and child.name in _CHROME_NAMES:
            continue
        if not isinstance(child, Tag):
            txt = str(child).strip()
            if txt:  # 1-char text leaves count too (bytes contract)
                regions.append({"kind": "passthroughText", "html": txt,
                                "leaves": 1, "topIndex": ti})
                top_levels.append({"html": txt, "leaves": 1})
                ti += 1
            continue
        # `el` = live Tag ref for the P2.5 contribution lift (decompose_group
        # mutates the ORIGINAL parse — no re-serialization drift). Never JSON-
        # dumped: extract_content and the templates writer both strip topLevels.
        top_levels.append({"html": str(child), "leaves": _count_leaves(child),
                           "el": child})
        if child in obj_set:
            regions.append({"kind": "component", "el": child, "topIndex": ti})
        elif id(child) in has_comp_below:
            rec(child, ti)
        else:
            # content-less top children (spacer/decoration divs) STILL occupy
            # pixels — dropping one cost 128px of section spacing (measured on
            # careers). Emit as zero-leaf passthrough: free, and the spacing
            # survives at section altitude.
            regions.append({"kind": "passthrough", "html": str(child),
                            "leaves": _count_leaves(child), "topIndex": ti})
        ti += 1

    return {"regions": regions, "leavesTotal": _count_leaves(root),
            "topLevels": top_levels,
            # embed/landing pages without <main> (observed: a Typeform page):
            # EVERYTHING must flow through the body partition — component
            # emission outside a main region would double-emit junk
            "noMain": no_main}


# ── Per-page component extraction ─────────────────────────────────

def extract_page(html, slug):
    # NO decompose: script/style/noscript are part of the BYTES contract — the
    # partition's passthrough blobs must carry them (observed live: a Typeform
    # embed page whose body is script-only lost everything). Detection and
    # field extraction SKIP those subtrees instead (see extract_fields).
    soup = BeautifulSoup(html, "lxml")

    sxa_mode = soup.find(class_="component") is not None
    comp_nodes = build_component_index(soup, sxa_mode)
    comp_set = set(id(x) for x in comp_nodes)
    comp_set_els = comp_nodes  # for identity `in` we wrap below

    # bs4 `in` on a set of ids: use a helper set of the actual objects
    obj_set = set()
    for n in comp_nodes:
        obj_set.add(n)

    def is_comp(el):
        return el in obj_set

    # top-level components = no component ancestor
    index_of = {id(el): i for i, el in enumerate(comp_nodes)}
    components = []
    for el in comp_nodes:
        parent_comp = None
        for anc in el.parents:
            if isinstance(anc, Tag) and anc in obj_set:
                parent_comp = anc
                break
        role, variants = role_and_variants(el, sxa_mode)
        parent_role = role_and_variants(parent_comp, sxa_mode)[0] if parent_comp else None
        # skip pure region wrappers that hold only other components (no own fields)
        acc = extract_fields(el, obj_set)
        shape = shape_from_fields(acc)
        is_container = bool(acc["child_components"])
        child_shape = item_html = None
        if is_container:
            # dominant child role shape
            child_roles = [role_and_variants(c, sxa_mode)[0] for c in acc["child_components"]]
        else:
            rc, cs, item_html = detect_repeated_child(el, obj_set)
            if rc:
                is_container = True
                child_shape = cs
        empty = (not shape and not is_container)
        interactive = bool(acc["interactive"]) or bool(
            INTERACTIVE_CLASS_RE.search(" ".join(classes_of(el))))
        components.append({
            "slug": slug,
            "role": role,
            "variants": variants,
            "position": nearest_region(el),
            "parentIsComponent": parent_comp is not None,
            "shape": shape,
            "shapeSig": "|".join(shape),
            "isContainer": is_container,
            "childShape": child_shape,
            "empty": empty,
            "parentRole": parent_role,
            "classString": " ".join(classes_of(el)),
            "textSample": " ".join(acc["text_parts"])[:200],
            "images": acc["images"][:6],
            "links": acc["links"][:8],
            "headings": [h[1] for h in acc["headings"]][:4],
            "topLevel": parent_comp is None,
            # ── bridge extras (in-memory; consumed by extract_content's semantic
            # adapter + the html-fragments emission, stripped from candidates) ──
            "parentIndex": index_of.get(id(parent_comp)) if parent_comp is not None else None,
            "interactive": interactive,
            "imageDetails": acc["image_details"][:12],
            "linkDetails": acc["link_details"][:12],
            "fullText": " ".join(acc["text_parts"]),
            "outerHTML": str(el),
            "itemOuterHTML": item_html,
        })

    # ── passthrough partition of <main> (P1.2) ──
    part = partition_main(soup, obj_set)
    regions = []
    covered = 0
    for r in part["regions"]:
        if r["kind"] == "component":
            el = r.pop("el")
            r["compIndex"] = index_of.get(id(el))
            r["leaves"] = _count_leaves(el)
        covered += r["leaves"]
        regions.append(r)
    partition = {
        "regions": regions,
        "topLevels": part.get("topLevels", []),
        "leavesTotal": part["leavesTotal"],
        "leavesCovered": covered,
        "componentRegions": sum(1 for r in regions if r["kind"] == "component"),
        "passthroughRegions": sum(1 for r in regions if r["kind"] != "component"),
        "semanticLeafShare": round(
            sum(r["leaves"] for r in regions if r["kind"] == "component")
            / part["leavesTotal"], 3) if part["leavesTotal"] else None,
    }
    return sxa_mode, components, partition


# ── Cross-page aggregation ────────────────────────────────────────

def aggregate(all_components, num_pages):
    by_role = defaultdict(list)
    for c in all_components:
        by_role[c["role"]].append(c)

    candidates = []
    for role, insts in sorted(by_role.items(), key=lambda kv: -len(kv[1])):
        non_empty = [i for i in insts if not i["empty"]]
        pages = sorted(set(i["slug"] for i in insts))
        # dominant shape among non-empty instances
        shape_counter = Counter(i["shapeSig"] for i in non_empty)
        dom_sig = shape_counter.most_common(1)[0][0] if shape_counter else ""
        dom_shape = dom_sig.split("|") if dom_sig else []
        # optional fields = fields seen in some but not all non-empty instances
        field_freq = Counter()
        for i in non_empty:
            for f in i["shape"]:
                field_freq[f] += 1
        optional = sorted(f for f, n in field_freq.items()
                          if f not in dom_shape and n < len(non_empty))
        variant_tokens = sorted(set(v for i in insts for v in i["variants"]))
        positions = Counter(i["position"] for i in insts)
        position = positions.most_common(1)[0][0]
        is_container = any(i["isContainer"] for i in insts)
        child_shapes = [i["childShape"] for i in insts if i.get("childShape")]
        top_level_count = sum(1 for i in insts if i["topLevel"])
        parents = Counter(i["parentRole"] for i in insts if i.get("parentRole"))
        sample = max(non_empty or insts, key=lambda i: len(i["textSample"]))
        candidates.append({
            "candidateId": f"cand_{role}",
            "role": role,
            "interactive": any(i.get("interactive") for i in insts),
            # representative markup, popped by main() into html-fragments/ files
            "_sampleFragment": {
                "slug": sample["slug"],
                "classString": sample["classString"],
                "html": sample.get("outerHTML") or "",
                "itemHtml": sample.get("itemOuterHTML"),
            },
            "position": position,
            "positionSpread": dict(positions),
            "dataShape": dom_shape,
            "shapeSig": dom_sig,
            "optionalFields": optional,
            "frequency": len(insts),
            "nonEmptyFrequency": len(non_empty),
            "emptyInstances": len(insts) - len(non_empty),
            "pageCount": len(pages),
            "pages": pages,
            "isContainer": is_container,
            "childShape": child_shapes[0] if child_shapes else None,
            "topLevelCount": top_level_count,
            "topLevelRatio": round(top_level_count / len(insts), 2) if insts else 0,
            "commonParents": dict(parents),
            "variantTokens": variant_tokens,
            "distinctShapes": dict(shape_counter),
            "sampleClassString": sample["classString"],
            "sampleText": sample["textSample"],
            "sampleImages": sample["images"],
            "sampleLinks": sample["links"],
            "sampleHeadings": sample["headings"],
        })
    return candidates


def flag_cross_cutting(candidates, num_pages):
    threshold = max(2, int(round(0.8 * num_pages)))
    for c in candidates:
        header_footer = c["position"] in ("header", "footer", "nav")
        ubiquitous = c["pageCount"] >= threshold
        # Only a <nav> is meaningfully cross-cutting while nested (it lives inside
        # <header>). Other nested header/footer sub-parts (language switcher,
        # spacer) stay sub-parts — this keeps SXA from over-capturing.
        top_level = c["topLevelRatio"] >= 0.5 or c["position"] == "nav"
        has_content = c["nonEmptyFrequency"] > 0     # must carry real editable data
        c["isCrossCutting"] = bool(header_footer and ubiquitous and top_level and has_content)
    return candidates


# ── Template clustering ───────────────────────────────────────────

def cluster_templates(page_features, page_display_roles):
    """Cluster pages by their MACRO skeleton. Features are DATA-SHAPE archetype
    tokens (e.g. 'list:image|link|title', 'block:body|title'), NOT class-derived
    role names — so pages cluster across CMSes even when wrapper classes differ."""
    slugs = list(page_features.keys())

    def jac(a, b):
        sa, sb = set(a), set(b)
        if not sa and not sb:
            return 1.0
        return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0

    clusters = []
    THRESH = 0.4
    for s in slugs:
        placed = False
        for cl in clusters:
            if jac(page_features[s], cl["repFeatures"]) >= THRESH:
                cl["pages"].append(s)
                cl["repFeatures"] = list(set(cl["repFeatures"]) | set(page_features[s]))
                placed = True
                break
        if not placed:
            clusters.append({"pages": [s], "repFeatures": list(page_features[s])})
    out = []
    for i, cl in enumerate(sorted(clusters, key=lambda c: -len(c["pages"])), 1):
        rep_page = max(cl["pages"], key=lambda p: len(page_display_roles.get(p, [])))
        out.append({
            "clusterId": f"tpl_{i:02d}",
            "pageCount": len(cl["pages"]),
            "pages": sorted(cl["pages"]),
            "mainRolesRepresentative": page_display_roles.get(rep_page, []),
            "archetypeFeatures": sorted(cl["repFeatures"]),
        })
    return out


# ── Detail-page (mainResource) detection ──────────────────────────
#
# A Jahia detail page (blog article, product sheet…) is rendered by a
# jmix:mainResource template that renders the ENTITY node itself — not a dropped
# component. If we don't detect these, the article body is modeled as ordinary
# droppable components and the page can never be pixel-perfect. Detection is
# deterministic + agnostic (structure, not vocabulary):
#   1. a template cluster whose pages share a parent path segment P (slug depth>1)
#      = a detail-page cluster under P; strong confirmation if P is itself a
#      crawled page (the listing/index) -> a list/detail pair.
#   2. within it, the mainResource entity = a main-position role that is
#      cluster-exclusive (pages ⊆ cluster) and singular (~one instance per page);
#      its facet family (shared role stem) becomes the entity's parts.

def _slug_segments(slug):
    # the crawler joins path segments with "_" ( /blog/dam-vs-cms -> blog_dam-vs-cms )
    return (slug or "").split("_")


def _shape_has_richtext(shape):
    return any("richtext" in tok or tok.startswith("body:") for tok in (shape or []))


def _family_key(role):
    """Role stem before the first BEM-ish delimiter — the entity family.
    ct-article__right / ct-article--card-wrapper -> ct-article ; article -> article."""
    r = role or ""
    for delim in ("__", "--"):
        if delim in r:
            return r.split(delim)[0]
    return r


# CMS "content-type" wrapper prefixes: ct-article, node-article, paragraph--foo…
# The entity's real node is the bare stem (article), not the prefixed wrapper.
_CT_PREFIXES = ("ct-", "ct_", "content-type-", "contenttype-", "node--", "node-",
                "paragraph--", "paragraph-", "field--", "views-row-")


def _normalize_family(fam):
    f = fam or ""
    for p in _CT_PREFIXES:
        if f.startswith(p) and len(f) > len(p):
            return f[len(p):]
    return f


def detect_detail_templates(clusters, candidates, all_slugs):
    """Annotate each cluster with kind (detail|section|page) and, for detail
    clusters, the mainResource entity. Returns the list of detail templates."""
    results = []
    for cl in clusters:
        pages = cl["pages"]
        deep = [p for p in pages if len(_slug_segments(p)) > 1]
        if len(deep) < 2:
            cl["kind"] = "page" if len(pages) == 1 else "section"
            continue
        parents = Counter(_slug_segments(p)[0] for p in deep)
        parent, k = parents.most_common(1)[0]
        need = max(2, (len(pages) * 3 + 4) // 5)          # ceil(0.6 * len(pages))
        if k < need:
            cl["kind"] = "section"
            continue

        cluster_pages = set(pages)
        pool = []                                          # (cand, exclusive, singular, fracInCluster)
        for c in candidates:
            if c.get("position") != "main":
                continue
            cpages = set(c.get("pages", []))
            on = len(cpages & cluster_pages)
            if not on:
                continue
            exclusive = cpages <= cluster_pages
            singular = c.get("frequency", 0) / max(1, on) <= 1.6
            pool.append((c, exclusive, singular, on / max(1, len(cpages))))

        fam_counter = Counter(_family_key(c["role"])
                              for c, ex, si, _ in pool if ex and si)
        if not fam_counter:
            cl["kind"] = "section"
            continue
        family, famn = fam_counter.most_common(1)[0]
        facet_roles = sorted(c["role"] for c, ex, si, _ in pool
                             if ex and si and _family_key(c["role"]) == family)

        # entity = the bare root node the facets hang off. Prefer a cluster-
        # concentrated main role equal to the family or its CMS-prefix-stripped stem
        # (ct-article -> article); else the richest facet; else the synthetic stem.
        norm = _normalize_family(family)

        def entity_score(c):
            root_like = "__" not in c["role"] and "--" not in c["role"]
            return (1 if root_like else 0,
                    1 if _shape_has_richtext(c.get("dataShape")) else 0,
                    c.get("frequency", 0))

        root_pool = [c for c, ex, si, fr in pool
                     if fr >= 0.6 and c["role"] in (norm, family)]
        fam_members = [c for c, ex, si, fr in pool
                       if _family_key(c["role"]) == family and si and fr >= 0.6]
        entity = (max(root_pool, key=entity_score) if root_pool
                  else max(fam_members, key=entity_score) if fam_members else None)
        entity_role = entity["role"] if entity else norm
        confidence = "high" if (parent in all_slugs and famn >= 2) else "medium"

        cl["kind"] = "detail"
        cl["detailOf"] = parent
        cl["listingPageExists"] = parent in all_slugs
        cl["mainResource"] = {"entityRole": entity_role, "family": family,
                              "facetRoles": facet_roles, "confidence": confidence}
        results.append({
            "clusterId": cl["clusterId"], "detailOf": parent,
            "listingPageExists": parent in all_slugs, "pages": pages,
            "entityRole": entity_role, "family": family,
            "facetRoles": facet_roles, "confidence": confidence,
        })
    return results


# ── Main ──────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--max-pages", type=int, default=0)
    args = ap.parse_args()
    proj = args.project

    inv_path = f"{proj}/workflow-output/page-inventory.json"
    if not os.path.isfile(inv_path):
        print(f"FAIL: {inv_path} not found (run crawl first)", file=sys.stderr)
        sys.exit(1)
    inventory = json.load(open(inv_path))
    pages = inventory.get("pages", [])
    if args.max_pages:
        pages = pages[: args.max_pages]

    all_components = []
    page_main_roles = {}
    page_main_items = {}   # slug -> [(role, archetypeFeature)] for top-level main comps
    page_partitions = {}   # slug -> partition summary (P1.2 passthrough accounting)
    sxa_any = False

    for page in pages:
        html_path = os.path.join(proj, page.get("cachedAt", ""))
        if not os.path.isfile(html_path):
            print(f"  WARNING: cached file missing for {page['slug']}", file=sys.stderr)
            continue
        html = open(html_path, errors="replace").read()
        sxa_mode, comps, partition = extract_page(html, page["slug"])
        sxa_any = sxa_any or sxa_mode
        page_partitions[page["slug"]] = {k: v for k, v in partition.items()
                                         if k not in ("regions", "topLevels")}
        all_components.extend(comps)
        # main-region skeleton = top-level components in <main>; features are
        # DATA-SHAPE archetypes (cross-CMS comparable), roles kept for display.
        items = [(c["role"],
                  ("list:" if c["isContainer"] else "block:") + c["shapeSig"])
                 for c in comps
                 if c["position"] == "main" and c["topLevel"] and not c["empty"]]
        page_main_roles[page["slug"]] = [r for r, _ in items]
        page_main_items[page["slug"]] = items

    num_pages = len(page_main_roles)
    candidates = aggregate(all_components, num_pages)

    # Drop pure rendering artifacts: no editable content on any instance and not a
    # container (e.g. empty plain-html spacers, CSS-only background divs).
    dropped_empty = [c["role"] for c in candidates
                     if c["nonEmptyFrequency"] == 0 and not c["isContainer"]]
    candidates = [c for c in candidates
                  if c["nonEmptyFrequency"] > 0 or c["isContainer"]]

    candidates = flag_cross_cutting(candidates, num_pages)

    # Route always-nested, non-cross-cutting roles into a separate bucket: these
    # are internal parts / child types of a container, not standalone page-area
    # components. Modeled by the LLM as the container's childType (or absorbed).
    for c in candidates:
        c["alwaysNested"] = (c["topLevelRatio"] == 0.0 and not c["isCrossCutting"])

    cross_roles = set(c["role"] for c in candidates if c["isCrossCutting"])
    nested_roles = set(c["role"] for c in candidates if c["alwaysNested"])
    skeleton_exclude = cross_roles | nested_roles
    clean_main_roles = {s: [r for r in roles if r not in skeleton_exclude]
                        for s, roles in page_main_roles.items()}
    # Cluster on ROLE sets: within a single site (any CMS) class-derived roles are
    # stable and cluster pages well. (A data-shape feature over-fragments because
    # per-instance shapes vary; cross-CMS mixing is not a real single-site case.)
    clusters = cluster_templates(clean_main_roles, clean_main_roles)

    # detail-page (mainResource) detection — annotates clusters + tags candidates
    all_slugs = set(page_main_roles.keys())
    detail_templates = detect_detail_templates(clusters, candidates, all_slugs)
    entity_roles = {dt["entityRole"] for dt in detail_templates}
    facet_by_cluster = {dt["clusterId"]: set(dt["facetRoles"]) for dt in detail_templates}
    for c in candidates:
        for dt in detail_templates:
            if c["role"] == dt["entityRole"]:
                c["mainResourceEntity"] = True
                c["detailCluster"] = dt["clusterId"]
                c["detailOf"] = dt["detailOf"]
            elif c["role"] in facet_by_cluster.get(dt["clusterId"], ()):
                c["detailCluster"] = dt["clusterId"]

    out_dir = f"{proj}/workflow-output"
    os.makedirs(out_dir, exist_ok=True)

    # ── html-fragments: representative source markup per candidate ──
    # The downstream bridge needs REAL DOM fragments: /5-components replicates the
    # exact HTML structure (migration rule: fragments must match exactly), and the
    # passthrough layer (P1.2) renders uncaptured regions verbatim. One file per
    # candidate (+ .item.html for a repeated child), path recorded on the candidate.
    frag_dir = os.path.join(out_dir, "html-fragments")
    os.makedirs(frag_dir, exist_ok=True)
    for c in candidates:
        frag = c.pop("_sampleFragment", None) or {}
        if not frag.get("html"):
            continue
        safe = re.sub(r"[^A-Za-z0-9._-]", "-", c["role"])
        header = (f"<!-- role: {c['role']} | representative page: {frag['slug']}"
                  f" | class: {frag['classString']} -->\n")
        with open(os.path.join(frag_dir, f"{safe}.html"), "w") as f:
            f.write(header + frag["html"])
        c["htmlFragment"] = f"html-fragments/{safe}.html"
        if frag.get("itemHtml"):
            with open(os.path.join(frag_dir, f"{safe}.item.html"), "w") as f:
                f.write(header + frag["itemHtml"])
            c["itemHtmlFragment"] = f"html-fragments/{safe}.item.html"

    xcut = [c for c in candidates if c["isCrossCutting"]]
    nested = [c for c in candidates if c.get("alwaysNested")]
    content = [c for c in candidates if not c["isCrossCutting"] and not c.get("alwaysNested")]

    cand_out = {
        "generatedFrom": "semantic_extract.py (deterministic v2)",
        "sxaMode": sxa_any,
        "numPages": num_pages,
        "totalInstances": len(all_components),
        "totalCandidates": len(candidates),
        "crossCutting": xcut,
        "components": content,
        "nestedParts": nested,
        "detailTemplates": detail_templates,
    }
    _page_set = sorted(page_partitions.keys())
    provenance.stamp_json(cand_out, "semantic_extract.py", page_set=_page_set)
    with open(f"{out_dir}/semantic-candidates.json", "w") as f:
        json.dump(cand_out, f, indent=2, ensure_ascii=False)

    tpl_out = {
        "numPages": num_pages,
        "crossCuttingRoles": sorted(cross_roles),
        "nestedPartRoles": sorted(nested_roles),
        "detailTemplates": detail_templates,
        "clusters": clusters,
        # P1.2 passthrough accounting per page (semantic share = quality dial §2)
        "pagePartitions": page_partitions,
    }
    provenance.stamp_json(tpl_out, "semantic_extract.py", page_set=_page_set)
    with open(f"{out_dir}/semantic-templates.json", "w") as f:
        json.dump(tpl_out, f, indent=2, ensure_ascii=False)

    # ── report ──
    print("=== SEMANTIC EXTRACTION (deterministic v2) ===")
    print(f"SXA mode: {sxa_any} | pages: {num_pages} | raw instances: {len(all_components)}")
    print(f"dropped empty artifacts: {len(dropped_empty)}  {sorted(set(dropped_empty))}")
    print(f"candidates: {len(candidates)}  ->  {len(xcut)} cross-cutting | {len(content)} content | {len(nested)} nested-parts")
    print()
    print("CROSS-CUTTING (header/footer/nav, every page):")
    for c in xcut:
        print(f"  {c['role']:24s} pos={c['position']:6s} pages={c['pageCount']}/{num_pages}  shape=[{c['shapeSig']}]")
    print()
    print("CONTENT CANDIDATES (by frequency):")
    for c in sorted(content, key=lambda x: -x["frequency"]):
        cont = " CONTAINER" if c["isContainer"] else ""
        var = f" variants={c['variantTokens']}" if c["variantTokens"] else ""
        print(f"  {c['role']:26s} freq={c['frequency']:2d} pages={c['pageCount']:2d} [{c['shapeSig']:38s}]{cont}{var}")
    print()
    print("NESTED PARTS (child types / internal parts — modeled under a parent):")
    for c in sorted(nested, key=lambda x: -x["frequency"]):
        print(f"  {c['role']:24s} freq={c['frequency']:2d}  parents={c['commonParents']}  shape=[{c['shapeSig']}]")
    print()
    print(f"TEMPLATES: {len(clusters)} clusters for {num_pages} pages")
    for cl in clusters:
        kind = cl.get("kind", "?")
        tag = f"  [{kind}]" + (f" of '{cl['detailOf']}'" if kind == "detail" else "")
        print(f"  {cl['clusterId']}  pages={cl['pageCount']:2d}{tag}  {cl['pages']}")
    shares = [p["semanticLeafShare"] for p in page_partitions.values()
              if p.get("semanticLeafShare") is not None]
    uncov = [(s, p) for s, p in page_partitions.items()
             if p["leavesCovered"] < p["leavesTotal"]]
    print()
    print(f"PARTITION (P1.2): semantic leaf share min={min(shares):.0%} "
          f"avg={sum(shares)/len(shares):.0%}" if shares else "PARTITION: no pages")
    if uncov:
        print(f"  !! {len(uncov)} page(s) with uncovered leaves (partition NOT total):")
        for s, p in uncov[:6]:
            print(f"     {s}: {p['leavesCovered']}/{p['leavesTotal']}")
        print(f"        skeleton: {cl['mainRolesRepresentative']}")
    print()
    print(f"DETAIL PAGES (mainResource): {len(detail_templates)} detected")
    for dt in detail_templates:
        listing = f"listing '{dt['detailOf']}' ✓" if dt["listingPageExists"] else f"parent '{dt['detailOf']}'"
        print(f"  {dt['clusterId']}: entity='{dt['entityRole']}' family='{dt['family']}' "
              f"[{listing}] conf={dt['confidence']}")
        print(f"        facets: {dt['facetRoles']}")
    print()
    print(f"Output: {out_dir}/semantic-candidates.json + semantic-templates.json")


if __name__ == "__main__":
    main()
