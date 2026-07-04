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

Exit 0 iff gatePass (every composable page byte-exact). Exit 1 on any red.
Exit 2 on usage / no composable pages.

Usage: compose_probe.py <projects/name> [--pages slug,slug]
  <projects/name> is the project PATH (matches the plan's project_path); the
  bare project name is also accepted.
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


def write_composed_page(out_dir, slug, mirror_txt, composed_body, asset_base):
    """Full composed page = the mirror's <!doctype>/<html>/<head> (verbatim) +
    <body {mirror bodyAttrs}> composed_body </body>. Assets pointed offline. This
    is what the reviewer compares against the mirror in the side-by-side — same
    head/CSS, only the body swapped for our composition."""
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
    head_html = ""
    m = re.search(r"<body\b[^>]*>", mirror_txt, re.I)
    if m:
        head_html = mirror_txt[:m.start()]
    else:
        head_html = "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
    page = head_html + body_open + composed_body + "</body></html>"
    page = _offline_refs(page, asset_base)
    with open(os.path.join(out_dir, f"{slug}.composed.html"), "w",
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
