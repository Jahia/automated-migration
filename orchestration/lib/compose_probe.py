#!/usr/bin/env python3
"""compose_probe.py — the COMPOSE GATE (pre-Jahia qualitative gate, ASSIST-PLAN).

Julian's requested checkpoint: BEFORE anything is deployed to Jahia, prove that
the EXTRACTED content (orchestration/content/<project>.content-load.json — the
skeletons + instances the content step will load into the JCR) re-composes each
page EXACTLY as the Jahia LIVE views will render it, and judge that composition
against the scoped local-mirror page it was extracted from.

Why this exists, when the partition/contribution gates already run at extract
time: those gates judge the payload's *accounting* (nothing dropped, coverage
floors, no dead props). They do NOT re-run the LIVE composition semantics
end-to-end. The compose gate does — it replays skeletonRender.ts's composeNode
(marker substitution + {{child:N}} splicing) and the Layout shell exactly, then
asserts the result is byte-identical to the mirror body. A skeleton that lifts
a field but drops a comment, mis-orders a child, or escapes text differently
than the TS view would is invisible to the accounting gates and lethal to
fidelity — this catches it before deploy, with a human-reviewable side-by-side.

Composition semantics — a faithful Python port of the AUTHORITATIVE splice rules
(orchestration/templates/fidelity-shell/skeletonRender.ts + semantic_extract.
recompose_group + Layout.tsx):

  substitute(node)  (skeletonRender.ts `substitute` / recompose_group `subst`):
    * {{media:imageN}}  -> the media unit's exact original markup (`orig`) — the
                          byte-exact DEFAULT render (an unedited node == source).
    * {{link:href}}     -> the contributor link, attribute-escaped.
    * {{f:body*}}       -> spliced RAW (richtext HTML).
    * {{f:<other>}}     -> minimal-escaped (&, <, > — quotes stay raw).
  composeNode(node)  (skeletonRender.ts `composeNode`):
    * splice each {{child:N}} slot with child N's substituted skeleton, in JCR
      child order (== creation == document order). Children beyond the max slot
      index render after the last slot; leftover markers stripped.
  page body  (Layout.tsx): the composed AREA content = every top-level instance
    (parent == None) composed in document order — including area-flagged chrome,
    which sits in the body exactly where the source rendered it (the vision
    adapter emits it as an ordered top-level rawHtml region). On discoverasr the
    shell is a bare <body> wrapper (levels=[body], no innerLevels), so the body
    body == the AREA content; the shell's before/after around <main> are applied
    when present so the comparison stays whole-body.

Judge: byte-identity of the composed body vs the SCOPED local-mirror page body.
"bytes are the contract" (rule 23) — normalize nothing. The mirror body is
serialized with comments re-wrapped (rule 32) and the SAME assetBase rewrite the
extractor applied (rewrite_asset_refs) so the two sides are apples-to-apples
(both in module-served form); no other transform. FROZEN bar: every composable
page must be byte-exact — no threshold flag.

Composable vs not: a page composes iff its content-load carries the
skeleton/instance structure (the semantic/vision adapter — `instances`). A page
whose stored payload cannot be composed into a whole body (legacy `blocks`-only
generic fallback, or a missing `shell`) is reported "not composable — skipped"
and EXCLUDED from the verdict, with an explicit composablePages count. An honest
gate says what it cannot see; it never fakes green over a page it can't judge.

Outputs (under <PP>/workflow-output/compose/):
  <slug>.composed.html   full page (mirror head reused; composed body swapped in;
                         asset refs pointed at ../local-mirror/assets so it
                         renders offline).
  compose-check.json     {pages:[{slug, byteExact, composedBytes, mirrorBytes,
                         firstDivergence?}], composablePages, gatePass}.
  compose-review.html    self-contained side-by-side (mirror | composed) with
                         synchronized scrolling + per-page verdict banner.

The DRILL-DOWN COMPONENT MAP (--map, or automatically after a GREEN gate):
  <slug>.map.html        the byte-exact composed page with each instance's ROOT
                         element tagged data-viz-path / data-viz-type /
                         data-viz-depth / data-viz-fields, at EVERY nesting level
                         (container children, and their {{child:N}} items
                         recursively). It is a STRICT SUPERSET of the gate bytes:
                         stripping the annotation reproduces compose_body(page)
                         byte-for-byte — re-asserted per page at build time
                         (assert_gate_unchanged). The gate composition and its
                         byte-verdict are bit-for-bit UNCHANGED by --map. Edge:
                         when a substituted skeleton does not begin with an element
                         (a bare comment / empty chrome), the MAP ONLY wraps it in
                         <div style="display:contents" …> so the region stays
                         queryable while rendering pixel-identically (the wrapper
                         generates no box; the gate path never sees it).
  component-map.html     self-contained, zero-external-request viewer: page
                         selector; iframes <slug>.map.html (same-origin file
                         access, like compose-review); overlay boxes from
                         getBoundingClientRect of [data-viz-path]; colour per type
                         + legend; drill-down (depth-1 overview → click a region to
                         reveal its direct children, ancestors dimmed; breadcrumb
                         to climb back); a depth slider "tout montrer" mode with
                         nested borders; hover tooltip (path / type / field counts).

Exit 0 iff gatePass (every composable page byte-exact). Exit 1 on any red.
Exit 2 on usage / no composable pages. The map build NEVER changes the exit code.

Usage: compose_probe.py <projects/name> [--pages slug,slug] [--map] [--no-map]
  <projects/name> is the project PATH (matches the plan's project_path); the
  bare project name is also accepted. --map forces the component-map build;
  --no-map suppresses the automatic post-GREEN build.
"""
import argparse
import html as _html
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import extract_content as EC  # noqa: E402  (rewrite_asset_refs / runtime map)

try:
    from bs4 import BeautifulSoup, Comment
except Exception:  # pragma: no cover - bs4 is a pipeline dependency
    BeautifulSoup = None
    Comment = None


# ── composition primitives (mirror skeletonRender.ts / recompose_group) ──

def _esc_text(v):
    """Minimal HTML escaping (&, <, > — quotes stay raw). MUST match
    skeletonRender.ts escapeHtml / semantic_extract._esc_text or the composition
    diverges from the certified bytes."""
    return _html.escape(v, quote=False)


def _esc_attr(v):
    """Attribute escaping (&, <, >, ") — skeletonRender.ts escapeAttr /
    semantic_extract._esc_attr. The rule for {{link:href}}."""
    return (v.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


_MARKER_RE = re.compile(r"\{\{(?:f|media|link):[^}]+\}\}")
_CHILD_RE = re.compile(r"\{\{child:(\d+)\}\}")


def substitute(inst):
    """skeletonRender.ts `substitute` (== recompose_group `subst`): replace this
    instance's field/media/link markers in its skeleton. A rawHtml passthrough
    with no skeleton renders its verbatim `html` field (the composeNode default
    for a marker-free node is its own markup)."""
    html = inst.get("skeleton")
    if html is None:
        return (inst.get("fields") or {}).get("html", "")
    # media FIRST (skeletonRender.ts order): a media unit renders its ORIGINAL
    # markup verbatim (the weakref==origRef default state — byte-exact).
    for m in inst.get("media") or []:
        marker = "{{media:%s}}" % m["name"]
        if marker in html:
            html = html.replace(marker, m["orig"])
    lnk = inst.get("link")
    if lnk and "{{link:href}}" in html:
        html = html.replace("{{link:href}}", _esc_attr(lnk.get("href") or ""))
    for k, v in (inst.get("fields") or {}).items():
        if k == "html" or not isinstance(v, str) or not v:
            continue
        marker = "{{f:%s}}" % k
        if marker in html:
            # body* splice RAW (richtext); every other field minimal-escaped.
            html = html.replace(marker, v if k.startswith("body") else _esc_text(v))
    return html


def compose_instance(idx, instances, children_of):
    """skeletonRender.ts `composeNode`: substitute this node's markers, then
    splice item children into {{child:N}} slots in child (== document) order.
    Children beyond the max slot render after the last slot; leftover markers
    stripped."""
    inst = instances[idx]
    html = substitute(inst)
    if "{{child:" in html:
        rendered = [substitute(instances[c]) for c in children_of.get(idx, [])
                    if instances[c].get("skeleton")]
        max_idx = -1
        for m in _CHILD_RE.finditer(html):
            max_idx = max(max_idx, int(m.group(1)))
        extras = "".join(rendered[max_idx + 1:])

        def repl(m):
            i = int(m.group(1))
            base = rendered[i] if i < len(rendered) else ""
            return base + (extras if i == max_idx else "")

        html = _CHILD_RE.sub(repl, html)
    # strip any leftover unresolved markers (composeNode's final replace)
    return _MARKER_RE.sub("", html)


def compose_body(page):
    """The composed AREA content = every top-level instance (parent == None)
    composed in document order. Returns None if the page carries no composable
    `instances` (legacy generic `blocks`-only fallback)."""
    instances = page.get("instances")
    if instances is None:
        return None
    children_of = {}
    for idx, inst in enumerate(instances):
        par = inst.get("parent")
        if par is not None:
            children_of.setdefault(par, []).append(idx)
    return "".join(
        compose_instance(idx, instances, children_of)
        for idx, inst in enumerate(instances)
        if inst.get("parent") is None
    )


# ── MAP variant: byte-exact composition + per-instance annotation ──────────
#
# The map artifact (<slug>.map.html) is the gate composition with each instance's
# ROOT element tagged `data-viz-*` so a viewer can draw a box per component at
# every nesting level. It MUST be a strict superset of the gate bytes: strip every
# data-viz-* attribute (and the map-only display:contents wrappers) from the map
# and you get back the gate body verbatim. That invariant is asserted at build
# time (assert_gate_unchanged) so the drill-down can NEVER regress the gate.
#
# How annotation preserves rendering:
#   * The annotation is injected into each instance's skeleton root element BEFORE
#     substitution, by the SAME substitute/compose_instance/compose_body traversal
#     the gate uses — so children spliced into {{child:N}} slots carry their own
#     annotation at their own nesting depth, and the document order is identical.
#   * data-viz-* attributes are inert (custom attributes never affect layout), so
#     the annotated page renders pixel-identically to the gate composition.
#   * display:contents edge — when an instance's substituted skeleton does NOT
#     begin with an element (a bare comment like <!-- Footer -->, or empty chrome),
#     there is no opening tag to hang the attributes on. The map (and ONLY the map)
#     wraps that fragment in <div style="display:contents" data-viz-*>…</div>.
#     display:contents makes the wrapper generate no box of its own (children boxes
#     stand in), so rendering is unchanged; the wrapper merely gives the region a
#     queryable node. A comment-only / empty fragment yields a zero-size rect and
#     the viewer simply draws no box for it (correct — there is nothing to show).

_VIZ_ATTR_RE = re.compile(r'\s+data-viz-(?:path|type|depth|fields)="[^"]*"')
_VIZ_WRAP_OPEN_RE = re.compile(
    r'<div style="display:contents" data-viz-path="[^"]*" data-viz-type="[^"]*"'
    r' data-viz-depth="\d+" data-viz-fields="[^"]*">')
_VIZ_WRAP_CLOSE = "</div><!--/viz-->"
# opening tag: <tag ...attrs...> or <tag ...attrs.../> — captures name + the run
# up to the closing '>' (never matches comments/doctype/closing tags).
_OPEN_TAG_RE = re.compile(r'<([a-zA-Z][a-zA-Z0-9:-]*)((?:[^>]*?))(/?)>')


def _field_counts(inst):
    """Editor-surface counts for the annotation: f = liftable text/richtext fields
    (excludes the rawHtml passthrough `html` field), media units, links, child
    slots. This is what an editor actually contributes on the node, not a raw
    marker count (markers that never resolve are not editable fields)."""
    fields = inst.get("fields") or {}
    nf = sum(1 for k, v in fields.items()
             if k != "html" and isinstance(v, str) and v)
    nm = len(inst.get("media") or [])
    nl = 1 if inst.get("link") else 0
    return nf, nm, nl


def _annotate_root(html, path, ntype, depth, fields_str):
    """Inject data-viz-* onto the substituted skeleton's ROOT element. If the
    fragment does not start with an element (comment/text/empty lead), wrap it in
    a map-only <div style="display:contents"> so the region is still queryable.
    The attributes are appended to the opening tag verbatim (they round-trip out
    via _VIZ_ATTR_RE)."""
    attrs = (' data-viz-path="%s" data-viz-type="%s" data-viz-depth="%d"'
             ' data-viz-fields="%s"'
             % (_esc_attr(path), _esc_attr(ntype), depth, _esc_attr(fields_str)))
    lead = html.lstrip()
    if lead and _OPEN_TAG_RE.match(lead):
        # inject just before the '>' (or '/>') of the FIRST opening tag, keeping
        # any leading whitespace of the fragment intact (byte-round-trip).
        pre_len = len(html) - len(lead)
        m = _OPEN_TAG_RE.match(lead)
        end = m.end()               # index of char after '>' within `lead`
        # position of the closing '>' or '/>' start
        insert_at = pre_len + m.start(3) if m.group(3) else pre_len + end - 1
        return html[:insert_at] + attrs + html[insert_at:]
    # no leading element -> map-only display:contents wrapper
    return ('<div style="display:contents"%s>%s%s'
            % (attrs, html, _VIZ_WRAP_CLOSE))


def substitute_map(inst, path, depth):
    """substitute() with the root element annotated for the map artifact. The
    substitution is byte-identical to substitute(); only the root tag differs."""
    html = substitute(inst)
    nf, nm, nl = _field_counts(inst)
    child_slots = 0
    sk = inst.get("skeleton")
    if sk:
        child_slots = len(set(_CHILD_RE.findall(sk)))
    fields_str = "f%d media%d link%d child%d" % (nf, nm, nl, child_slots)
    return _annotate_root(html, path, inst.get("type") or "rawHtml", depth,
                          fields_str)


def compose_instance_map(idx, instances, children_of, path, depth):
    """compose_instance() for the map: the node's own root is annotated, and each
    {{child:N}} slot is spliced with the child's OWN annotated+composed fragment,
    so every nesting level carries data-viz-* at its true depth. Child paths chain
    the parent path (path/N). Byte-identical to compose_instance() once the
    data-viz-* attrs and display:contents wrappers are stripped."""
    inst = instances[idx]
    html = substitute_map(inst, path, depth)
    if "{{child:" in html:
        kids = [c for c in children_of.get(idx, [])
                if instances[c].get("skeleton")]
        # a child slot renders the child's FULL composed subtree (recursive), so
        # grandchildren nest correctly at depth+2, depth+3, … (matches the gate's
        # substitute-per-child expansion; recursion adds depth the gate never
        # reached but never changes bytes because deeper skeletons carry no
        # {{child}} on the reference sites).
        rendered = [
            compose_instance_map(c, instances, children_of,
                                 "%s/%d" % (path, n), depth + 1)
            for n, c in enumerate(kids)
        ]
        max_idx = -1
        for m in _CHILD_RE.finditer(html):
            max_idx = max(max_idx, int(m.group(1)))
        extras = "".join(rendered[max_idx + 1:])

        def repl(m):
            i = int(m.group(1))
            base = rendered[i] if i < len(rendered) else ""
            return base + (extras if i == max_idx else "")

        html = _CHILD_RE.sub(repl, html)
    return _MARKER_RE.sub("", html)


def compose_body_map(page):
    """compose_body() for the map: every top-level (depth-1) instance annotated
    and composed with recursive child annotation. Returns None when not composable
    (same contract as compose_body)."""
    instances = page.get("instances")
    if instances is None:
        return None
    children_of = {}
    for idx, inst in enumerate(instances):
        par = inst.get("parent")
        if par is not None:
            children_of.setdefault(par, []).append(idx)
    tops = [idx for idx, inst in enumerate(instances)
            if inst.get("parent") is None]
    return "".join(
        compose_instance_map(idx, instances, children_of, str(n), 1)
        for n, idx in enumerate(tops)
    )


def strip_viz(html):
    """Round-trip the map body BACK to the gate body: remove every data-viz-*
    attribute and unwrap the map-only display:contents wrappers. This MUST equal
    compose_body(page) byte-for-byte (asserted in assert_gate_unchanged)."""
    html = _VIZ_WRAP_OPEN_RE.sub("", html)
    html = html.replace(_VIZ_WRAP_CLOSE, "")
    html = _VIZ_ATTR_RE.sub("", html)
    return html


def assert_gate_unchanged(page, map_body):
    """Regression assertion: stripping the annotation from the map body reproduces
    the gate composition EXACTLY. If this ever fails, the map build has diverged
    from the byte-exact gate path — raise loudly rather than emit a map that lies
    about the composition the gate certified."""
    gate = compose_body(page)
    if gate is None:
        return
    if strip_viz(map_body) != gate:
        raise AssertionError(
            "map annotation regressed the gate composition: strip_viz(map) != "
            "compose_body(page) — the drill-down map must be a strict superset of "
            "the certified gate bytes")


def page_composable_reason(page):
    """Is this page WHOLE-BODY byte-composable from what the content-load stores?

    A page is page-composable iff its stored instances reconstruct the ENTIRE
    scoped body byte-for-byte — which the VISION adapter guarantees (its partition
    is total over <body>: every top-level instance is a complete body region, in
    document order, byte-exact by construction and self-checked at extraction) and
    the SEMANTIC adapter does NOT. The semantic adapter partitions only the <main>
    region and wraps it in a `shell` whose before/after chunks page_shell() DELIBERATELY
    normalizes — external <script src=//…> stripped, leading/trailing whitespace
    `.strip()`ped (extract_content.page_shell / _EXT_SCRIPT_RE / chunk()). That
    shell is engineered for PIXEL fidelity (judged by the ground-truth gate against
    Jahia), never byte-identity, so a page-wide byte compare of a semantic page is
    meaningless — it would report RED on the extractor's own intentional
    normalization, not on a composition defect.

    So the honest rule: only claim page-wide composability for the byte-faithful
    whole-body profile. Signals (either suffices; both agree on every reference):
      * partition.adapterMode == "vision"   (the extractor's own stamp), OR
      * a byte-faithful shell shape: no real <main> (mainAttrs == bodyAttrs) and no
        innerLevels — i.e. a bare <body> wrapper with no lossy chunking.
    Everything else -> not composable page-wide (skipped, excluded from the verdict).
    Returns None when composable, else a short reason string."""
    if page.get("instances") is None:
        return "no composable instances (generic blocks-only payload)"
    part = page.get("partition") or {}
    if part.get("adapterMode") == "vision":
        return None
    shell = page.get("shell") or {}
    main_attrs = shell.get("mainAttrs") or {}
    body_attrs = shell.get("bodyAttrs") or {}
    inner_levels = shell.get("innerLevels") or []
    levels = shell.get("levels") or []
    has_main = (main_attrs and main_attrs != body_attrs) or \
        any(lvl.get("tag") == "main" for lvl in levels)
    if has_main or inner_levels:
        return ("semantic adapter (main-region partition + normalized shell) — "
                "not whole-body byte-composable; pixel fidelity is judged by the "
                "ground-truth gate, not byte-identity here")
    return None


# ── mirror side: the scoped local-mirror body, apples-to-apples ──

def _ser(node):
    """bs4 serialization with comments re-wrapped (rule 32) — str(Comment) yields
    the bare text; the <!-- --> markers must be preserved or the mirror body is
    not the bytes a visitor sees."""
    if Comment is not None and isinstance(node, Comment):
        return "<!--%s-->" % node
    return str(node)


def scoped_mirror_body(mirror_path, asset_base):
    """The scoped mirror page's BODY inner HTML, with the SAME assetBase rewrite
    the extractor applied to the content-load (rewrite_asset_refs). This puts
    both sides in module-served form so the byte comparison judges COMPOSITION,
    not the localizer's URL form. Scope rules (exclude/force_passthrough) are
    already baked into the mirror by scope_apply.py at localize time, so the
    on-disk mirror IS the scoped DOM — no extra pruning here."""
    txt = open(mirror_path, encoding="utf-8", errors="ignore").read()
    body = BeautifulSoup(txt, "lxml").find("body")
    if body is None:
        return None, txt
    inner = "".join(_ser(c) for c in body.children)
    return EC.rewrite_asset_refs(inner, asset_base), txt


# ── composed full page (for the side-by-side) ──

def _module_static_base(project):
    """assetBase from the project's passthrough-overrides (what the content-load
    refs were rewritten to). Falls back to the conventional module path."""
    try:
        ov = json.load(open(
            f"projects/{project}/workflow-output/passthrough-overrides.json"))
        b = ov.get("assetBase")
        if b:
            return b
    except Exception:
        pass
    return f"/modules/{project}/static/"


def _offline_refs(html, asset_base):
    """Point every asset ref at ../local-mirror/assets/ so the composed page (in
    workflow-output/compose/) renders OFFLINE with the mirror's own copies.
    Rewrites BOTH the module-static form (composed body: /modules/x/static/
    assets/…) and the mirror-relative form (reused head: assets/…). Self-
    contained — no external requests."""
    rel = "../local-mirror/assets/"
    # module-static form -> relative
    html = html.replace(asset_base + "assets/", rel)
    html = html.replace(asset_base + "runtime-assets/", "../local-mirror/runtime-assets/")
    # bare mirror-relative "assets/" (from the reused head) -> ../local-mirror/assets/.
    # word-boundary so it never touches "/modules/.../assets/" or "runtime-assets/".
    html = re.sub(r'(?<![\w/.-])(\.?/)?assets/', rel, html)
    html = re.sub(r'(?<![\w/.-])(\.?/)?runtime-assets/', "../local-mirror/runtime-assets/", html)
    return html


def _shell_around_body(mirror_txt, body_inner, asset_base):
    """Wrap a body inner-HTML in the mirror's own <!doctype>/<html>/<head> + the
    mirror's <body …> attrs, with asset refs pointed offline. Shared by the
    composed page and the annotated map page so both render with the same head/CSS
    and differ only in the body inner-HTML."""
    soup = BeautifulSoup(mirror_txt, "lxml")
    body = soup.find("body")
    body_open = "<body>"
    if body is not None:
        attrs = []
        for k, v in (body.attrs or {}).items():
            v = " ".join(v) if isinstance(v, list) else str(v)
            attrs.append('%s="%s"' % (k, v))
        body_open = "<body" + ("".join(" " + a for a in attrs)) + ">"
    # everything up to and including <body ...> from the mirror (doctype+head)
    m = re.search(r"<body\b[^>]*>", mirror_txt, re.I)
    head_html = mirror_txt[:m.start()] if m else \
        "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
    page = head_html + body_open + body_inner + "</body></html>"
    return _offline_refs(page, asset_base)


def write_composed_page(out_dir, slug, mirror_txt, composed_body, asset_base):
    """Full composed page = the mirror's <!doctype>/<html>/<head> (verbatim) +
    <body {mirror bodyAttrs}> composed_body </body>. Assets pointed offline. This
    is what the reviewer compares against the mirror in the side-by-side — same
    head/CSS, only the body swapped for our composition."""
    page = _shell_around_body(mirror_txt, composed_body, asset_base)
    with open(os.path.join(out_dir, f"{slug}.composed.html"), "w",
              encoding="utf-8") as f:
        f.write(page)


def write_map_page(out_dir, slug, mirror_txt, map_body, asset_base):
    """Full annotated page = the composed page with every instance's root element
    tagged data-viz-*. Same head/CSS/assets as <slug>.composed.html — only the
    body carries the annotation. Consumed by component-map.html (loaded in an
    iframe, same-origin file access, no external requests)."""
    page = _shell_around_body(mirror_txt, map_body, asset_base)
    with open(os.path.join(out_dir, f"{slug}.map.html"), "w",
              encoding="utf-8") as f:
        f.write(page)


# ── side-by-side review (matches reconstruct_probe.mjs conventions) ──

def _esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def review_html(project, results):
    n_exact = sum(1 for r in results if r.get("byteExact"))
    n_comp = sum(1 for r in results if r.get("composable"))
    n_skip = sum(1 for r in results if not r.get("composable"))
    all_ok = n_comp > 0 and n_exact == n_comp

    def option(r):
        return '<option value="%s">%s%s</option>' % (
            _esc(r["slug"]), _esc(r["slug"]),
            "" if r.get("composable") else " (skipped)")

    def panel(r):
        slug = _esc(r["slug"])
        if not r.get("composable"):
            banner = ('<div class="banner skip">NOT COMPOSABLE — skipped '
                      '(payload carries no composable instances; excluded from '
                      'the verdict)</div>')
            return ('<section class="pg" data-slug="%s" hidden>%s</section>'
                    % (slug, banner))
        if r.get("byteExact"):
            banner = ('<div class="banner ok">BYTE-EXACT — composed body == '
                      'scoped mirror body (%d bytes)</div>' % r["composedBytes"])
        else:
            d = r.get("firstDivergence") or {}
            banner = ('<div class="banner bad">RED — first divergence at byte %s '
                      '(composed %d B vs mirror %d B)<div class="div">'
                      '<div><span>composed</span><code>%s</code></div>'
                      '<div><span>mirror</span><code>%s</code></div></div></div>'
                      % (d.get("offset", "?"), r["composedBytes"], r["mirrorBytes"],
                         _esc(d.get("composed", "")), _esc(d.get("mirror", ""))))
        return ('<section class="pg" data-slug="%s" hidden>%s'
                '<div class="frames">'
                '<div class="frame"><h3>Scoped local mirror</h3>'
                '<iframe loading="lazy" data-src="../local-mirror/%s.html"></iframe></div>'
                '<div class="frame"><h3>Composed (Jahia LIVE view)</h3>'
                '<iframe loading="lazy" data-src="%s.composed.html"></iframe></div>'
                '</div></section>'
                % (slug, banner, slug, slug))

    verdict_cls = "ok" if all_ok else "bad"
    verdict_txt = ("GREEN — every composable page byte-exact"
                   if all_ok else "RED — a composable page diverges")
    return """<!doctype html><meta charset="utf-8">
<title>Compose gate review — %s</title>
<style>
 body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
 header{padding:14px 22px;background:#171a21;position:sticky;top:0;border-bottom:1px solid #2a2f3a;z-index:9;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
 h1{font-size:17px;margin:0}
 header small{color:#9aa4b2}
 select{background:#20242e;color:#e6e6e6;border:1px solid #333a47;border-radius:6px;padding:6px 10px;font-size:14px}
 label{display:flex;gap:7px;align-items:center;color:#cfd6e2}
 .ok{color:#39d98a}.bad{color:#ff6b6b}.warn{color:#ffb454}
 .pg{padding:0}
 .banner{padding:11px 22px;font-weight:600;border-bottom:1px solid #20242e}
 .banner.ok{background:#0f2a1c;color:#39d98a}
 .banner.bad{background:#2a1113;color:#ff8a8a}
 .banner.skip{background:#241f10;color:#ffb454}
 .banner .div{margin-top:8px;font-weight:400;display:grid;gap:4px}
 .banner .div span{display:inline-block;width:74px;color:#9aa4b2;font-size:12px}
 .banner .div code{background:#000;padding:2px 6px;border-radius:4px;color:#ffd479;font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap}
 .frames{display:flex;gap:0}
 .frame{flex:1;min-width:0;border-right:1px solid #2a2f3a;display:flex;flex-direction:column}
 .frame:last-child{border-right:0}
 .frame h3{margin:0;padding:8px 14px;font-size:12px;color:#9aa4b2;background:#12151b;border-bottom:1px solid #2a2f3a;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
 iframe{width:100%%;height:calc(100vh - 150px);border:0;background:#fff}
</style>
<header>
 <h1>Compose gate — %s <span class="%s">(%d/%d composable byte-exact%s)</span></h1>
 <label>Page <select id="sel" onchange="show(this.value)">%s</select></label>
 <label><input type="checkbox" id="sync" checked> synchronized scroll</label>
 <small class="%s">%s</small>
</header>
%s
<script>
 function show(slug){
   document.querySelectorAll('.pg').forEach(function(p){
     var on = p.dataset.slug===slug; p.hidden=!on;
     if(on) p.querySelectorAll('iframe[data-src]').forEach(function(f){ if(!f.src) f.src=f.dataset.src; });
   });
 }
 // synchronized scrolling: mirror scroll from one iframe onto its sibling
 document.addEventListener('load', function(e){
   if(e.target.tagName!=='IFRAME') return;
   try{
     var doc=e.target.contentWindow;
     doc.addEventListener('scroll', function(){
       if(!document.getElementById('sync').checked) return;
       var frames=e.target.closest('.frames').querySelectorAll('iframe');
       frames.forEach(function(o){ if(o!==e.target){ try{o.contentWindow.scrollTo(doc.scrollX,doc.scrollY);}catch(_){} }});
     });
   }catch(_){/* cross-doc guard */}
 }, true);
 var first=document.querySelector('#sel option'); if(first) show(first.value);
</script>""" % (
        _esc(project), _esc(project), verdict_cls, n_exact, n_comp,
        ("" if not n_skip else ", %d skipped" % n_skip),
        "".join(option(r) for r in results),
        verdict_cls, verdict_txt,
        "\n".join(panel(r) for r in results),
    )


# ── drill-down component map viewer (self-contained, zero external requests) ──

def component_map_html(project, map_results):
    """Emit the self-contained drill-down viewer (component-map.html). No external
    requests: it iframes <slug>.map.html (same dir, same-origin file access like
    compose-review) and draws overlay boxes from getBoundingClientRect of the
    [data-viz-path] elements inside. Colour per data-viz-type + legend; drill-down
    starts at depth 1, click reveals a region's DIRECT children (ancestors dimmed),
    breadcrumb climbs back; a depth slider is the alternative "tout montrer" mode
    (nested borders); hover tooltip shows path / type / field counts.

    map_results: [{slug, hasMap}] — only slugs that produced a .map.html are
    offered in the selector."""
    mapped = [r for r in map_results if r.get("hasMap")]
    options = "".join(
        '<option value="%s">%s</option>' % (_esc(r["slug"]), _esc(r["slug"]))
        for r in mapped)
    first_slug = _esc(mapped[0]["slug"]) if mapped else ""
    # Two-part template: %-format the small header bits, then .replace the JS body
    # (which is full of braces/percent signs) via a marker so no escaping fights.
    head = """<!doctype html><meta charset="utf-8">
<title>Component map — __PROJECT__</title>
<style>
 :root{--bg:#0f1115;--panel:#171a21;--line:#2a2f3a;--fg:#e6e6e6;--mut:#9aa4b2}
 *{box-sizing:border-box}
 body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--fg)}
 header{padding:10px 18px;background:var(--panel);position:sticky;top:0;border-bottom:1px solid var(--line);z-index:20;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
 h1{font-size:16px;margin:0}
 select,input[type=range]{background:#20242e;color:var(--fg);border:1px solid #333a47;border-radius:6px;padding:5px 9px;font-size:13px}
 label{display:flex;gap:6px;align-items:center;color:#cfd6e2;font-size:13px}
 button{background:#20242e;color:var(--fg);border:1px solid #333a47;border-radius:6px;padding:5px 10px;font-size:13px;cursor:pointer}
 button:hover{background:#2a2f3a}
 #crumbs{display:flex;gap:4px;align-items:center;flex-wrap:wrap;font-size:13px;color:var(--mut)}
 #crumbs a{color:#7fb2ff;cursor:pointer;text-decoration:none}
 #crumbs a:hover{text-decoration:underline}
 #crumbs .sep{color:#4a515e}
 #stage{position:relative;width:100%;height:calc(100vh - 92px);overflow:hidden;background:#fff}
 #frame{width:100%;height:100%;border:0;background:#fff}
 #overlay{position:absolute;inset:0;pointer-events:none}
 .box{position:absolute;pointer-events:auto;cursor:pointer;box-sizing:border-box;transition:opacity .12s}
 .box.dim{opacity:.12;pointer-events:none}
 .box .tag{position:absolute;top:0;left:0;transform:translateY(-100%);font:11px/1.4 ui-monospace,Menlo,monospace;padding:1px 5px;white-space:nowrap;border-radius:3px 3px 0 0;color:#0b0d10;font-weight:600;max-width:340px;overflow:hidden;text-overflow:ellipsis}
 #legend{position:fixed;right:12px;bottom:12px;background:rgba(17,20,27,.94);border:1px solid var(--line);border-radius:8px;padding:9px 11px;font-size:12px;z-index:30;max-height:44vh;overflow:auto;max-width:260px}
 #legend h4{margin:0 0 6px;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
 #legend .row{display:flex;gap:7px;align-items:center;margin:3px 0;color:#d6dbe4}
 #legend .sw{width:13px;height:13px;border-radius:3px;flex:0 0 auto;border:1px solid rgba(255,255,255,.25)}
 #tip{position:fixed;z-index:40;pointer-events:none;background:#0b0d10;border:1px solid #3a4150;border-radius:6px;padding:7px 9px;font:12px/1.5 ui-monospace,Menlo,monospace;color:#e6e6e6;max-width:380px;display:none;box-shadow:0 6px 22px rgba(0,0,0,.5)}
 #tip b{color:#ffd479}
 #tip .t{color:var(--mut)}
 #empty{position:absolute;inset:0;display:none;align-items:center;justify-content:center;color:var(--mut);font-size:14px;background:rgba(15,17,21,.6)}
 small.hint{color:var(--mut)}
</style>
<header>
 <h1>Component map <span class="mut" style="color:var(--mut)">— __PROJECT__</span></h1>
 <label>Page <select id="sel">__OPTIONS__</select></label>
 <span id="crumbs"></span>
 <span style="flex:1"></span>
 <label title="tout montrer — nested borders up to this depth">depth
   <input type="range" id="depth" min="1" max="1" value="1" step="1"><span id="depthval">1</span></label>
 <button id="reset" title="back to depth-1 overview">reset</button>
 <small class="hint" id="count"></small>
</header>
<div id="stage">
 <iframe id="frame" src="__FIRST__.map.html"></iframe>
 <div id="overlay"></div>
 <div id="empty">no annotated regions on this page</div>
</div>
<div id="legend"><h4>component types</h4><div id="legrows"></div></div>
<div id="tip"></div>
<script>
/*__JS__*/
</script>"""
    js = _COMPONENT_MAP_JS.replace("__FIRSTSLUG__", first_slug)
    return (head
            .replace("__PROJECT__", _esc(project))
            .replace("__OPTIONS__", options)
            .replace("__FIRST__", first_slug)
            .replace("/*__JS__*/", js))


# The viewer JS is kept in a raw string (braces/percent-free of Python formatting).
# __FIRSTSLUG__ is substituted with the initial page slug.
_COMPONENT_MAP_JS = r"""
'use strict';
var stage = document.getElementById('stage');
var frame = document.getElementById('frame');
var overlay = document.getElementById('overlay');
var emptyEl = document.getElementById('empty');
var sel = document.getElementById('sel');
var crumbs = document.getElementById('crumbs');
var depthSlider = document.getElementById('depth');
var depthVal = document.getElementById('depthval');
var tip = document.getElementById('tip');
var legrows = document.getElementById('legrows');
var countEl = document.getElementById('count');

// stable, colour-blind-friendly palette; assigned per data-viz-type on first sight
var PALETTE = ['#4e9bff','#ff8f4e','#39d98a','#c678dd','#ffd479','#5ad1e0',
               '#ff6b9d','#a3d95a','#f2777a','#7f9cf5','#e0a458','#63c7b2'];
var typeColor = {};
var colorIdx = 0;
function colorFor(t){
  if(!typeColor[t]){ typeColor[t] = PALETTE[colorIdx % PALETTE.length]; colorIdx++; }
  return typeColor[t];
}

var nodes = [];      // {el, path, type, depth, fields, parentPath}
var byPath = {};     // path -> node
var focusPath = null; // currently drilled-into path (null = depth-1 overview)
var showAll = false;  // "tout montrer" (depth slider) mode

function parseFields(s){
  // "f2 media1 link0 child3" -> readable
  return s || '';
}

function collect(){
  nodes = []; byPath = {};
  var doc = frame.contentDocument;
  if(!doc) return;
  var els = doc.querySelectorAll('[data-viz-path]');
  els.forEach(function(el){
    var n = {
      el: el,
      path: el.getAttribute('data-viz-path'),
      type: el.getAttribute('data-viz-type') || 'rawHtml',
      depth: parseInt(el.getAttribute('data-viz-depth') || '1', 10),
      fields: el.getAttribute('data-viz-fields') || ''
    };
    // parent path = drop last "/N" segment (top-level has no slash)
    var i = n.path.lastIndexOf('/');
    n.parentPath = i >= 0 ? n.path.slice(0, i) : null;
    nodes.push(n);
    byPath[n.path] = n;
  });
  var maxDepth = nodes.reduce(function(m,n){ return Math.max(m, n.depth); }, 1);
  depthSlider.max = String(Math.max(1, maxDepth));
  buildLegend();
}

function buildLegend(){
  var seen = {};
  nodes.forEach(function(n){ seen[n.type] = (seen[n.type]||0) + 1; });
  var types = Object.keys(seen).sort();
  legrows.innerHTML = types.map(function(t){
    return '<div class="row"><span class="sw" style="background:'+colorFor(t)+'"></span>'
      + '<span>'+esc(t)+'</span> <span style="color:var(--mut)">('+seen[t]+')</span></div>';
  }).join('') || '<div class="row" style="color:var(--mut)">none</div>';
}

function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

// which nodes are VISIBLE as boxes right now
function visibleNodes(){
  if(showAll){
    var d = parseInt(depthSlider.value, 10);
    return nodes.filter(function(n){ return n.depth <= d; });
  }
  if(focusPath === null){
    return nodes.filter(function(n){ return n.depth === 1; });
  }
  // drill-down: the focused node + its DIRECT children
  var focus = byPath[focusPath];
  var out = focus ? [focus] : [];
  nodes.forEach(function(n){ if(n.parentPath === focusPath) out.push(n); });
  return out;
}

function draw(){
  overlay.innerHTML = '';
  var doc = frame.contentDocument;
  if(!doc){ return; }
  var vis = visibleNodes();
  var sr = stage.getBoundingClientRect();
  var sx = frame.contentWindow.scrollX || 0;
  var sy = frame.contentWindow.scrollY || 0;
  var drawn = 0;
  vis.forEach(function(n){
    var r = n.el.getBoundingClientRect();
    // display:contents wrappers / empty chrome -> zero box; skip (nothing to show)
    if(r.width < 1 && r.height < 1) return;
    var box = document.createElement('div');
    box.className = 'box';
    var col = colorFor(n.type);
    box.style.left = (r.left + sx) + 'px';
    box.style.top = (r.top + sy) + 'px';
    box.style.width = r.width + 'px';
    box.style.height = r.height + 'px';
    // nested-border thickness by depth in "tout montrer"; single accent otherwise
    var bw = showAll ? Math.max(1, 4 - (n.depth - 1)) : 2;
    box.style.border = bw + 'px solid ' + col;
    box.style.background = hexA(col, showAll ? 0.04 : 0.09);
    // in drill-down, the focused node is the dim "container" frame (ancestor)
    if(!showAll && focusPath !== null && n.path === focusPath){
      box.classList.add('dim');
    }
    var hasKids = nodes.some(function(m){ return m.parentPath === n.path; });
    var label = n.type + (hasKids ? ' ▸' : '');
    box.innerHTML = '<span class="tag" style="background:'+col+'">'+esc(label)+'</span>';
    box.dataset.path = n.path;
    box.addEventListener('click', function(ev){ ev.stopPropagation(); onBoxClick(n); });
    box.addEventListener('mousemove', function(ev){ showTip(ev, n); });
    box.addEventListener('mouseleave', hideTip);
    overlay.appendChild(box);
    drawn++;
  });
  emptyEl.style.display = drawn === 0 ? 'flex' : 'none';
  countEl.textContent = drawn + ' region' + (drawn===1?'':'s') + ' shown / ' + nodes.length + ' total';
}

function hexA(hex, a){
  var m = /^#([0-9a-f]{6})$/i.exec(hex); if(!m) return hex;
  var n = parseInt(m[1],16);
  return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a+')';
}

function onBoxClick(n){
  if(showAll) return;                     // slider mode is non-interactive drill
  var hasKids = nodes.some(function(m){ return m.parentPath === n.path; });
  if(hasKids){ focusPath = n.path; renderCrumbs(); draw(); scrollToNode(n); }
}

function scrollToNode(n){
  try{
    var r = n.el.getBoundingClientRect();
    var sy = frame.contentWindow.scrollY || 0;
    frame.contentWindow.scrollTo({top: Math.max(0, r.top + sy - 40), behavior:'smooth'});
  }catch(_){}
}

function renderCrumbs(){
  var parts = [];
  parts.push('<a data-goto="__ROOT__">overview</a>');
  if(focusPath !== null){
    // build the chain root..focus
    var chain = [];
    var p = focusPath;
    while(p){ chain.unshift(p); var i = p.lastIndexOf('/'); p = i>=0 ? p.slice(0,i) : null; }
    chain.forEach(function(path){
      var n = byPath[path];
      var lbl = n ? n.type : path;
      parts.push('<span class="sep">›</span>');
      parts.push('<a data-goto="'+esc(path)+'">'+esc(lbl)+'</a>');
    });
  }
  crumbs.innerHTML = parts.join(' ');
  crumbs.querySelectorAll('a[data-goto]').forEach(function(a){
    a.addEventListener('click', function(){
      var g = a.getAttribute('data-goto');
      focusPath = (g === '__ROOT__') ? null : g;
      renderCrumbs(); draw();
    });
  });
}

function showTip(ev, n){
  tip.style.display = 'block';
  tip.innerHTML = '<div><b>'+esc(n.type)+'</b></div>'
    + '<div class="t">path '+esc(n.path)+' &nbsp;depth '+n.depth+'</div>'
    + '<div class="t">'+esc(parseFields(n.fields))+'</div>';
  var pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  var x = ev.clientX + pad, y = ev.clientY + pad;
  if(x + w > window.innerWidth) x = ev.clientX - w - pad;
  if(y + h > window.innerHeight) y = ev.clientY - h - pad;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip(){ tip.style.display = 'none'; }

function refresh(){ collect(); focusPath = null; renderCrumbs(); draw(); }

frame.addEventListener('load', refresh);
// redraw on iframe scroll/resize so boxes track content
window.addEventListener('resize', draw);
function attachScroll(){
  try{ frame.contentWindow.addEventListener('scroll', draw, {passive:true}); }catch(_){}
}
frame.addEventListener('load', attachScroll);

sel.addEventListener('change', function(){
  frame.src = sel.value + '.map.html';   // load triggers refresh()
});
depthSlider.addEventListener('input', function(){
  showAll = true; depthVal.textContent = depthSlider.value;
  focusPath = null; renderCrumbs(); draw();
});
document.getElementById('reset').addEventListener('click', function(){
  showAll = false; depthSlider.value = '1'; depthVal.textContent = '1';
  focusPath = null; renderCrumbs(); draw();
});
// click empty stage -> climb one level up
stage.addEventListener('click', function(){
  if(showAll || focusPath === null) return;
  var i = focusPath.lastIndexOf('/');
  focusPath = i >= 0 ? focusPath.slice(0, i) : null;
  renderCrumbs(); draw();
});

// first load (iframe src set inline) may already be complete
if(frame.contentDocument && frame.contentDocument.readyState === 'complete'){ refresh(); }
"""


# ── driver ──

def _project_from_arg(arg):
    """Accept both 'projects/name' (project_path, the plan convention) and a bare
    'name'. Returns the bare project name."""
    a = arg.rstrip("/")
    if a.startswith("projects/"):
        return a[len("projects/"):]
    if os.path.sep in a:
        return os.path.basename(a)
    return a


def main():
    ap = argparse.ArgumentParser(description="Compose gate (pre-Jahia)")
    ap.add_argument("project", help="projects/<name> or <name>")
    ap.add_argument("--pages", default=None,
                    help="comma-separated slugs to judge (default: all)")
    ap.add_argument("--map", action="store_true",
                    help="also emit the DRILL-DOWN component map: per composable "
                         "page a <slug>.map.html (byte-exact compose + data-viz-* "
                         "annotation on every instance root at every nesting depth) "
                         "and a self-contained component-map.html viewer. The map "
                         "NEVER changes the gate verdict/exit code; it is also built "
                         "automatically after a GREEN gate (cheap). Byte-identity of "
                         "the gate is re-asserted per page (strip_viz(map)==gate).")
    ap.add_argument("--no-map", dest="no_map", action="store_true",
                    help="suppress the automatic post-GREEN map build")
    a = ap.parse_args()
    if BeautifulSoup is None:
        print("compose_probe: bs4/lxml required (pipeline dependency)", file=sys.stderr)
        return 2
    project = _project_from_arg(a.project)
    pp = f"projects/{project}"
    load_p = f"orchestration/content/{project}.content-load.json"
    if not os.path.isfile(load_p):
        print(f"compose_probe: no content-load at {load_p}", file=sys.stderr)
        return 2
    data = json.load(open(load_p))
    pages = data.get("pages", {})
    if a.pages:
        want = [s.strip() for s in a.pages.split(",") if s.strip()]
        pages = {s: pages[s] for s in want if s in pages}
        missing = [s for s in want if s not in data.get("pages", {})]
        if missing:
            print(f"  note: slugs not in content-load (skipped): {', '.join(missing)}",
                  file=sys.stderr)

    EC.load_runtime_map(project)   # so rewrite_asset_refs matches the extractor
    EC.load_media_map(project)
    asset_base = _module_static_base(project)
    mirror_dir = f"{pp}/workflow-output/local-mirror"
    out_dir = f"{pp}/workflow-output/compose"
    os.makedirs(out_dir, exist_ok=True)

    results = []
    # composable pages retained for the map build (mirror head + composed body).
    composed_ctx = {}
    for slug in pages:
        page = pages[slug]
        mirror_path = f"{mirror_dir}/{slug}.html"
        rec = {"slug": slug, "composable": False}
        # is this page WHOLE-BODY byte-composable from the stored payload? (vision
        # profile yes; semantic main-partition + normalized shell no — reported
        # skipped, never faked green, never RED on the extractor's own normalization)
        reason = page_composable_reason(page)
        if reason is not None:
            rec["reason"] = reason
            # a semantic-adapter page is a VALID different architecture, not a
            # defect — flag it so an all-semantic site reads N/A, not RED.
            rec["notApplicable"] = reason.startswith("semantic adapter")
            results.append(rec)
            print(f"  SKIP {slug}: {reason}")
            continue
        if not os.path.isfile(mirror_path):
            rec["reason"] = "no local-mirror page"
            results.append(rec)
            print(f"  SKIP {slug}: no local-mirror page")
            continue
        composed = compose_body(page)
        mirror_body, mirror_txt = scoped_mirror_body(mirror_path, asset_base)
        if mirror_body is None:
            rec["reason"] = "mirror page has no <body>"
            results.append(rec)
            print(f"  SKIP {slug}: mirror has no body")
            continue
        rec["composable"] = True
        rec["composedBytes"] = len(composed.encode("utf-8"))
        rec["mirrorBytes"] = len(mirror_body.encode("utf-8"))
        exact = composed == mirror_body
        rec["byteExact"] = exact
        if not exact:
            n = min(len(composed), len(mirror_body))
            i = next((k for k in range(n) if composed[k] != mirror_body[k]), n)
            rec["firstDivergence"] = {
                "offset": i,
                "composed": composed[max(0, i - 50):i + 50],
                "mirror": mirror_body[max(0, i - 50):i + 50],
            }
        write_composed_page(out_dir, slug, mirror_txt, composed, asset_base)
        composed_ctx[slug] = (page, mirror_txt)
        results.append(rec)
        mark = "OK  " if exact else "RED "
        line = f"  {mark}{slug:34s} composed={rec['composedBytes']:8d} mirror={rec['mirrorBytes']:8d}"
        print(line)
        if not exact:
            d = rec["firstDivergence"]
            print(f"       @byte {d['offset']}: composed {d['composed']!r}")
            print(f"                    mirror   {d['mirror']!r}")

    composable = [r for r in results if r.get("composable")]
    n_exact = sum(1 for r in composable if r["byteExact"])
    skipped = [r for r in results if not r.get("composable")]
    n_na = sum(1 for r in skipped if r.get("notApplicable"))
    # broken/missing skips = skips that are NOT the valid semantic-adapter case
    # (missing mirror, no <body>, generic blocks-only) — those DO block.
    n_broken = len(skipped) - n_na

    # Gate verdict:
    #   any composable page RED           -> RED (a real composition defect)
    #   >=1 composable, all byte-exact     -> GREEN
    #   0 composable, all skips N/A        -> N/A pass (valid semantic-adapter site;
    #                                          pixel fidelity judged by ground-truth)
    #   0 composable, some skip is broken  -> RED (missing/broken evidence)
    if composable:
        gate_pass = n_exact == len(composable)
    else:
        gate_pass = n_broken == 0 and len(results) > 0
    not_applicable = not composable and gate_pass

    check = {
        "project": project,
        "composablePages": len(composable),
        "totalPages": len(results),
        "byteExactPages": n_exact,
        "skippedNotApplicable": n_na,
        "skippedBroken": n_broken,
        "notApplicable": not_applicable,
        "gatePass": gate_pass,
        "pages": results,
    }
    with open(os.path.join(out_dir, "compose-check.json"), "w",
              encoding="utf-8") as f:
        json.dump(check, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "compose-review.html"), "w",
              encoding="utf-8") as f:
        f.write(review_html(project, results))

    # ── drill-down component map (never affects the gate verdict/exit code) ──
    # Built when --map is passed OR automatically after a GREEN gate (cheap), unless
    # --no-map. Per composable page: annotate the byte-exact composition, ASSERT the
    # annotation strips back to the gate bytes, write <slug>.map.html; then emit the
    # self-contained component-map.html viewer over the pages that produced a map.
    build_map = a.map or (gate_pass and composable and not a.no_map)
    if build_map:
        map_results = []
        map_errors = []
        for slug, (page, mirror_txt) in composed_ctx.items():
            try:
                map_body = compose_body_map(page)
                assert_gate_unchanged(page, map_body)   # regression guard
                write_map_page(out_dir, slug, mirror_txt, map_body, asset_base)
                map_results.append({"slug": slug, "hasMap": True})
            except Exception as e:  # a map defect must not sink the gate
                map_errors.append((slug, str(e)))
                map_results.append({"slug": slug, "hasMap": False})
        with open(os.path.join(out_dir, "component-map.html"), "w",
                  encoding="utf-8") as f:
            f.write(component_map_html(project, map_results))
        n_maps = sum(1 for r in map_results if r["hasMap"])
        print(f"  ▶ component map: {out_dir}/component-map.html  "
              f"({n_maps}/{len(map_results)} pages annotated)")
        for slug, err in map_errors:
            print(f"    MAP WARN {slug}: {err}", file=sys.stderr)

    n_skip = len(results) - len(composable)
    print()
    print(f"=== COMPOSE GATE — {project} ===")
    print(f"  {n_exact}/{len(composable)} composable pages byte-exact"
          + (f" ({n_skip} skipped)" if n_skip else ""))
    if not_applicable:
        print(f"  N/A (PASS) — no whole-body-composable pages; all {n_na} pages use "
              "the semantic adapter (main-region partition + normalized shell), a "
              "valid architecture whose fidelity is judged by the ground-truth gate, "
              "not byte-identity here")
    elif not composable:
        print(f"  RED — NO composable pages and {n_broken} broken/missing (nothing "
              "to judge; an honest gate cannot pass over missing evidence)")
    elif gate_pass:
        print("  GREEN — the extracted content re-composes byte-identically to "
              "the scoped mirror on every composable page")
    else:
        reds = [r["slug"] for r in composable if not r["byteExact"]]
        print(f"  RED — {len(reds)} page(s) diverge: {', '.join(reds[:8])}"
              + (" ..." if len(reds) > 8 else ""))
    print(f"  ▶ side-by-side review: {out_dir}/compose-review.html")
    print(f"  output: {out_dir}/  (compose-review.html + *.composed.html + compose-check.json)")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
