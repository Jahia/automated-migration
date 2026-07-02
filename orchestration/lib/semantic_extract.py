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
    if el.find(list(HEADING_TAGS)):
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


def _own_heading(node):
    """True if node carries its OWN heading (a section title/intro) that is not
    inside one of its item blocks — i.e. node is a 'titled section', not a pure
    layout wrapper. Such a node IS the component (title + intro + items as children)."""
    block_kids = [c for c in node.children if isinstance(c, Tag) and _is_block(c)]
    for h in node.find_all(list(HEADING_TAGS)):
        if h.get_text(strip=True) and not any(bk in h.parents for bk in block_kids):
            return True
    return False


def _find_component_row(node, depth=0):
    """Recursively locate the 'component altitude' below a content region:
    descend transparent single-block wrappers; at the first level with >=2 block
    children, emit those children (a heterogeneous zone) — unless they are a
    homogeneous repeated row, in which case emit the parent as one container.

    A node that carries its OWN title/intro (heading not inside an item block) is a
    TITLED SECTION and is emitted whole (Option A) — so section headings/intros are
    never dropped above the component row."""
    if depth > 7:
        return [node]
    block_children = [c for c in node.children if _is_block(c)]
    if len(block_children) == 0:
        return [node]
    # titled section: keep the whole node (title + intro + items). depth>0 so we
    # never swallow the top-level content region itself.
    if depth > 0 and _own_heading(node):
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
        for comp in _find_component_row(anc):
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
        if n.name in HEADING_TAGS:
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

def extract_fields(comp_el, comp_set):
    """Walk comp_el's subtree, stopping at nested component nodes, and build the
    editable field shape a contributor would set."""
    acc = {
        "headings": [], "images": [], "links": [],
        "text_parts": [], "has_richtext": False,
        "child_components": [],
    }

    def walk(node):
        for child in node.children:
            if not isinstance(child, Tag):
                txt = str(child).strip()
                if txt:
                    acc["text_parts"].append(txt)
                continue
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
            if name in ("video", "iframe"):
                acc["images"].append(child.get("src") or "media")
            if name == "a":
                href = child.get("href", "")
                if href and not href.startswith("#") and not href.startswith("javascript:"):
                    acc["links"].append(href)
            if name == "button":
                acc["links"].append("button")
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
    Returns (is_container, child_shape) or (False, None)."""
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
        return False, None
    item_acc = extract_fields(best[0], comp_set)
    return True, shape_from_fields(item_acc)


# ── Per-page component extraction ─────────────────────────────────

def extract_page(html, slug):
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()

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
        child_shape = None
        if is_container:
            # dominant child role shape
            child_roles = [role_and_variants(c, sxa_mode)[0] for c in acc["child_components"]]
        else:
            rc, cs = detect_repeated_child(el, obj_set)
            if rc:
                is_container = True
                child_shape = cs
        empty = (not shape and not is_container)
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
        })
    return sxa_mode, components


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
    sxa_any = False

    for page in pages:
        html_path = os.path.join(proj, page.get("cachedAt", ""))
        if not os.path.isfile(html_path):
            print(f"  WARNING: cached file missing for {page['slug']}", file=sys.stderr)
            continue
        html = open(html_path, errors="replace").read()
        sxa_mode, comps = extract_page(html, page["slug"])
        sxa_any = sxa_any or sxa_mode
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
    with open(f"{out_dir}/semantic-candidates.json", "w") as f:
        json.dump(cand_out, f, indent=2, ensure_ascii=False)

    tpl_out = {
        "numPages": num_pages,
        "crossCuttingRoles": sorted(cross_roles),
        "nestedPartRoles": sorted(nested_roles),
        "detailTemplates": detail_templates,
        "clusters": clusters,
    }
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
