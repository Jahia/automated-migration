#!/usr/bin/env python3
"""reconcile-check.py — BLOCKING gate on the analyze/model RECONCILIATION
(process-hardening, 2026-07-16). Runs BEFORE any load, on the artifacts alone:

  1. CONSERVATION  — per page, WORD-level: the fraction of source words
     (>= 3 letters, from non-excluded instances) present anywhere in the
     FINAL authorable payload >= --coverage (default 0.98). Word containment
     follows text that decomposition moves across rows; missing words are
     PRINTED (evidence, not counts). Proven by negative test: destroying the
     body-merge path reads 0.29-0.85; a clean run reads 1.0.
  2. LEFTOVER CEILING — no instance keeps >= --leftover (default 60) chars of
     visible text in its structure markup: everything editors should own must
     be IN properties/children (pre-JCR twin of skeleton-holds-content).
  3. VALUE-LEVEL APPLICABILITY — on the content-load payload:
     - title fields: no markup, <= 250 chars
     - body fields: no unresolved {{...}} marker debris
     - media entries: file present and image-suffixed

Usage: reconcile-check.py <project> [--coverage 0.90] [--leftover 60]
Exit 0 clean / 1 violations (each printed).
"""
import argparse
import json
import re
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--coverage", type=float, default=0.98)
    ap.add_argument("--leftover", type=int, default=60)
    a = ap.parse_args()
    bad = []

    rp = f"projects/{a.project}/workflow-output/reconciliation.json"
    try:
        recon = json.load(open(rp))
    except (FileNotFoundError, ValueError) as e:
        print(f"FAIL: reconcile-check — cannot read {rp}: {e}", file=sys.stderr)
        sys.exit(1)
    pages = recon.get("pages") or {}
    if not pages:
        print("FAIL: reconcile-check — reconciliation.json has no pages "
              "(a gate that cannot measure must fail)", file=sys.stderr)
        sys.exit(1)

    for pk, pg in sorted(pages.items()):
        cov = pg.get("coverage", 0)
        if pg.get("before", 0) >= 80 and cov < a.coverage:
            miss = " ".join((pg.get("missingWords") or [])[:15])
            bad.append(f"CONSERVATION {pk}: word coverage {cov} < {a.coverage} "
                       f"({pg.get('words', '?')} source words; missing: {miss})")
        for r in pg.get("rows") or []:
            if r.get("leftover", 0) >= a.leftover:
                bad.append(f"LEFTOVER {pk}[{r['idx']}] {r.get('nodeType') or r.get('type')}: "
                           f"{r['leftover']} chars stay in structure markup")

    cl = f"orchestration/content/{a.project}.content-load.json"
    try:
        data = json.load(open(cl))
    except (FileNotFoundError, ValueError) as e:
        print(f"FAIL: reconcile-check — cannot read {cl}: {e}", file=sys.stderr)
        sys.exit(1)

    # page inventory (crawl ledger) — the menu-as-content gate resolves anchor
    # hrefs against it. Missing inventory only disables THAT gate (older
    # projects); every other check still runs.
    inv_slugs = set()
    ip = f"projects/{a.project}/workflow-output/page-inventory.json"
    try:
        _inv = json.load(open(ip))
        _pgs = _inv.get("pages") or _inv
        inv_slugs = (set(_pgs) if isinstance(_pgs, dict)
                     else {p.get("slug") for p in _pgs if p.get("slug")})
    except (FileNotFoundError, ValueError):
        print(f"WARN: {ip} unreadable — menu-as-content gate skipped", file=sys.stderr)

    # valid node-type ledger from the manifest — a payload nodeType outside it
    # can NEVER create on Jahia (observed live 2026-07-20: 87 x:cardItem
    # children from the "x:y" placeholder fallback, every create rejected
    # with Unknown node type and the content silently absent)
    valid_nt = set()
    mp = f"projects/{a.project}/workflow-output/component-manifest.json"
    try:
        _man = json.load(open(mp))
        for c in (_man.get("components") or []) + (_man.get("crossCutting") or []):
            valid_nt.add(c.get("nodeType"))
            ct = c.get("childType")
            if isinstance(ct, dict) and ct.get("nodeType"):
                valid_nt.add(ct["nodeType"])
        valid_nt |= set((_man.get("instanceTypeMap") or {}).values())
        pt = _man.get("passthroughType")
        if pt:
            _mns = pt.split(":")[0]
            valid_nt |= {pt, f"{_mns}:cardItem", f"{_mns}:cta",
                         f"{_mns}:article", f"{_mns}:subNavigation"}
        valid_nt.discard(None)
    except (OSError, ValueError):
        print(f"WARN: {mp} unreadable — node-type ledger gate skipped", file=sys.stderr)

    def check_inst(inst, pk, path):
        f = inst.get("fields") or {}
        # GATE (2026-07-20): undeclared nodeType — the create is rejected by
        # Jahia (Unknown node type) and the node's whole subtree vanishes
        nt0 = inst.get("nodeType")
        if valid_nt and nt0 and nt0 not in valid_nt:
            bad.append(f"VALUE {pk}{path}: nodeType {nt0!r} is not declared by "
                       f"the manifest (Jahia rejects the create; content vanishes)")
        # GATE (2026-07-20, operator mandate 'image in richtext should not
        # happen'): a raster image UNIT at the TOP LEVEL of a richtext value
        # must be an image MEDIA UNIT (weakref picker) or a decomposed child —
        # never frozen markup. Images nested inside tables/lists/deep markup
        # legitimately stay in the richtext (DAM-rewritten at load, swappable
        # through the richtext editor — the Jahia-native contract; extracting
        # them shattered the surrounding markup, observed: postmarking /
        # online-security-you). svg icons stay inline. Mirrors debodify.
        # Subsumes the 2026-07-17 gallery-hoard gate.
        _RASTER = re.compile(r"\.(?:png|jpe?g|gif|webp|avif)(?:[?#]|$|['\")])", re.I)
        _NOSPLIT = {"table", "thead", "tbody", "tfoot", "tr", "td", "th",
                    "ul", "ol", "li", "dl", "dt", "dd"}
        b0 = f.get("body")
        for bk in [k for k in f if re.match(r"body\d*$", k)]:
            bv = f[bk]
            if not isinstance(bv, str) or not re.search(r"<img|background-image", bv) \
                    or not _RASTER.search(bv):
                continue
            from bs4 import BeautifulSoup as _BS0
            _sb = _BS0(bv, "lxml")
            _root = _sb.body or _sb
            n_frozen = 0
            for im in _sb.find_all("img"):
                if not _RASTER.search(im.get("src") or ""):
                    continue
                u = im
                p2 = u.parent
                while getattr(p2, "name", None) not in (None, "body", "html", "[document]"):
                    if len(p2.find_all("img")) != 1 or p2.get_text(strip=True):
                        break
                    u = p2
                    p2 = u.parent
                if u.parent is _root and not any(
                        getattr(pp, "name", None) in _NOSPLIT for pp in u.parents):
                    n_frozen += 1
            for el in _sb.find_all(style=re.compile(r"background-image", re.I)):
                m3 = re.search(r"""url\(\s*['"]?([^'")]+)""", el.get("style") or "")
                if not m3 or not _RASTER.search(m3.group(1)) or el.find("img"):
                    continue
                if el.parent is not _root or any(
                        getattr(pp, "name", None) in _NOSPLIT for pp in el.parents):
                    continue
                _pr = _BS0(str(el), "lxml")
                for sr in _pr.select(".sr-only"):
                    sr.extract()
                if not _pr.get_text(strip=True):
                    n_frozen += 1
            if n_frozen:
                bad.append(f"VALUE {pk}{path}: {bk} carries {n_frozen} top-level "
                           f"raster image unit(s) frozen in richtext (must be "
                           f"the image media unit / decomposed children)")
        # GATE (2026-07-17): tail-appended body marker — {{f:body}} AFTER a
        # SINGLE-ROOT skeleton renders swept content OUTSIDE the layout (home
        # hero). Multi-root fragments legitimately carry the marker at top
        # level (a swept trailing sibling) — not flagged.
        sk0 = inst.get("skeleton") or ""
        if re.search(r"</[a-z][^>]*>\s*\{\{f:body\}\}\s*$", sk0):
            from bs4 import BeautifulSoup as _BS
            _rest = sk0.rsplit("{{f:body}}", 1)[0]
            _roots = [c for c in (_BS(_rest, "lxml").body or []).children
                      if getattr(c, "name", None)] if _rest.strip() else []
            if len(_roots) == 1:
                bad.append(f"VALUE {pk}{path}: {{{{f:body}}}} appended after the "
                           f"single skeleton root (body renders outside the layout)")
        # GATE (2026-07-17): empty cta child — the button renders NOTHING
        # (enterprise 'Enquire': label stranded on the parent)
        is_cta = (str(inst.get("nodeType") or "").endswith(":cta")
                  or inst.get("type") == "cta")
        sk_cta = inst.get("skeleton") or ""
        if is_cta and not f and not inst.get("media") and not inst.get("imageFile"):
            # a field-less cta is legitimate IFF its own skeleton renders
            # something (icon-arrow shells excised from card markup carry an
            # svg/img and the {{link:href}} resolves from the cta's linkOrig)
            renders = bool(re.search(r"<svg|<img", sk_cta)) or bool(
                re.sub(r"\{\{[^}]+\}\}|<[^>]+>", "", sk_cta).strip())
            if not (sk_cta and renders):
                bad.append(f"VALUE {pk}{path}: cta child carries no fields (label lost)")
        # a label MARKER in the cta's own skeleton with no label VALUE renders
        # an empty button — same empty-shell class, one level down
        if is_cta and "{{f:linkLabel}}" in sk_cta and not f.get("linkLabel"):
            bad.append(f"VALUE {pk}{path}: cta skeleton has {{{{f:linkLabel}}}} "
                       f"marker but no linkLabel value")
        # GATE (2026-07-20): unresolvable link markers — ONLY :cta declares
        # linkLabel/linkOrig, so {{link:href}}/{{f:linkLabel}} in any OTHER
        # type's skeleton renders an EMPTY anchor/button shell (corporate
        # 'About SingPost': empty bordered pill + duplicate unlinked span).
        # The shell must move into the lifted cta child's own skeleton.
        if not is_cta and re.search(r"\{\{link:href\}\}|\{\{f:linkLabel\}\}", sk0):
            bad.append(f"VALUE {pk}{path}: {inst.get('nodeType') or inst.get('type')} "
                       f"skeleton carries link markers it cannot resolve "
                       f"(empty shell renders; shell belongs to the cta child)")
        # GATE (2026-07-20, operator: speedpost-standard): MENU-AS-CONTENT — a
        # body/skeleton carrying >= 3 anchors that resolve to inventory PAGES
        # with the CURRENT page among them is the source's in-page sub-nav
        # (sibling-service sidebar) frozen as content: menus include the page
        # you are on; content links out, never to itself. Navigation is TREE-
        # DRIVEN (AIStartupKit rule 19) — subnavify must have replaced it with
        # the {ns}:subNavigation component.
        if inv_slugs and not str(inst.get("nodeType") or "").endswith(":subNavigation"):
            for fld, s in [("skeleton", sk0)] + [(k, v) for k, v in f.items()
                                                 if isinstance(v, str)]:
                hrefs = re.findall(r"""href=["']([^"'#?]+)""", s or "")
                hits = {h.strip("/").replace("/", "_")
                        for h in hrefs if h.startswith("/")} & inv_slugs
                if len(hits) >= 3 and pk in hits:
                    bad.append(f"VALUE {pk}{path}: {fld} carries the in-page "
                               f"sub-nav as content ({len(hits)} sibling page "
                               f"links incl. the page itself — must be the "
                               f"tree-driven :subNavigation component)")
                    break
        t = f.get("title")
        if isinstance(t, str):
            if len(t) > 250:
                bad.append(f"VALUE {pk}{path}: title {len(t)} chars (>250)")
            if "<" in t and ">" in t:
                bad.append(f"VALUE {pk}{path}: title contains markup: {t[:60]!r}")
        b = f.get("body")
        if isinstance(b, str) and re.search(r"\{\{[^}]+\}\}", b):
            bad.append(f"VALUE {pk}{path}: body contains marker debris")
        # GATE (2026-07-20): unwrapped svg icon at richtext TOP LEVEL — the
        # sizing wrapper was lost in a lift/fold; a viewBox-only svg with no
        # container renders container-wide (delivery-rates: 24px download
        # icon painted ~1000px tall). Icons must stay inline in markup.
        if isinstance(b, str) and "<img" in b and ".svg" in b:
            from bs4 import BeautifulSoup as _BS2
            _bs = _BS2(b, "lxml")
            for _c in (_bs.body.children if _bs.body else []):
                if getattr(_c, "name", None) == "img" and \
                        (_c.get("src") or "").split("?")[0].lower().endswith(".svg"):
                    bad.append(f"VALUE {pk}{path}: unwrapped svg icon at body "
                               f"top level (lost its sizing wrapper, renders "
                               f"container-wide): {(_c.get('src') or '')[-40:]}")
        # GATE (2026-07-20 evening, operator authoring review): OVER-
        # FRAGMENTATION — a node carrying more than 4 positioned body slots
        # gives editors a wall of "Text (2)…Text (23)" fields (observed:
        # contribBody23). That many distinct text wrappers means the section
        # should have DECOMPOSED into child components; the slot mechanism is
        # for the 2-3 genuinely positioned runs (hero grid columns).
        n_slots = sum(1 for fk in f if re.match(r"body\d+$", fk))
        if n_slots > 4:
            bad.append(f"VALUE {pk}{path}: {n_slots + 1} body slots on one node "
                       f"(over-fragmented — should decompose into children)")
        # GATE (2026-07-20): body/label slot-marker pairing — a {{f:bodyN}} /
        # {{f:labelN}} marker without its field renders a HOLE; a bodyN/labelN
        # field without its marker renders NOWHERE (structure-aware merge must
        # keep both sides of each kept slot).
        for mk in set(re.findall(r"\{\{f:((?:body|label)\d+)\}\}", sk0)):
            if not (f.get(mk) or "").strip():
                bad.append(f"VALUE {pk}{path}: skeleton marker {{{{f:{mk}}}}} "
                           f"has no {mk} value (renders a hole)")
        for fk in f:
            if re.match(r"(?:body|label)\d+$", fk) and (f[fk] or "").strip() \
                    and "{{f:%s}}" % fk not in sk0:
                bad.append(f"VALUE {pk}{path}: field {fk} has no skeleton "
                           f"marker (content renders nowhere)")
        # GATE (2026-07-20): unresolvable SOURCE-ASSET url — a root-relative
        # asset path outside /modules|/cms|/files|/sites is the SOURCE site's
        # own path and can never resolve on Jahia (corporate masthead
        # background-image /dam/files/... painted a 790px white void).
        for fld, s in (("skeleton", sk0), ("body", b if isinstance(b, str) else "")):
            # Tailwind arbitrary-value CLASS tokens (class="bg-[url('/x.jpg')]")
            # are not fetched — the compiled CSS rule carries the rewritten
            # relative url. Strip class attributes before scanning.
            s = re.sub(r"""class=("[^"]*"|'[^']*')""", "class=x", s)
            # quoted url() first (paths may contain spaces/parens), then bare
            urls = [g1 or g2 or g3 for g1, g2, g3 in re.findall(
                r"""url\(\s*(?:'([^']+)'|"([^"]+)"|([^'\")]+))""", s)]
            urls += re.findall(r"""src=["']([^"']+)""", s)
            for u in urls:
                u = u.strip()
                if (u.startswith("/")
                        and not u.startswith(("/modules/", "/cms/", "/files/", "/sites/"))
                        and re.search(r"\.(png|jpe?g|gif|webp|svg|avif)$", u, re.I)):
                    bad.append(f"VALUE {pk}{path}: {fld} references the source "
                               f"site's asset path {u[:70]!r} (never resolves "
                               f"on Jahia)")
        for m in inst.get("media") or []:
            fn = (m.get("file") or "")
            if fn and not re.search(r"\.(png|jpe?g|gif|webp|svg|avif)$", fn, re.I):
                bad.append(f"VALUE {pk}{path}: media file {fn!r} not image-suffixed")
        for n, ch in enumerate(inst.get("children") or []):
            check_inst(ch, pk, f"{path}/item-{n + 1}")

    for pk, pg in (data.get("pages") or {}).items():
        for i, inst in enumerate(pg.get("instances") or []):
            check_inst(inst, pk, f"[{i}]")

    if bad:
        for x in bad[:25]:
            print(f"  - {x}")
        print(f"FAIL: reconcile-check — {len(bad)} violation(s)", file=sys.stderr)
        sys.exit(1)
    tot_words = sum(p.get("words", 0) for p in pages.values())
    tot_miss = sum(len(p.get("missingWords") or []) for p in pages.values())
    print(f"PASS: reconcile-check — {len(pages)} page(s), "
          f"{tot_words - tot_miss}/{tot_words} source words in authorable payload, "
          f"coverage floor {a.coverage}, leftover ceiling {a.leftover}")


if __name__ == "__main__":
    main()
