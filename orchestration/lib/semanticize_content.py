#!/usr/bin/env python3
"""semanticize_content.py — map a skeleton content-load onto the ARCHETYPE model.

Transforms `orchestration/content/<p>.content-load.json` (skeleton instances:
body/body2..N richtext runs + verbatim skeleton) into semantic instances whose
fields match the archetype CND (mix:title heading + one richtext `body` + the
composed media/cta mixin fields), so `load_content` creates clean, editable
nodes instead of skeleton blobs. Consumes the archetype manifest (model==
archetype) for the per-node field surface.

v1 SCOPE + KNOWN LIMITATION: the skeleton content-load already joined the
region's DOM into richtext runs, so this recovers the semantic TITLE (re-parse
the first heading out of the richtext) and folds the rest into `body`, keeps the
lifted link as the CTA, and recurses typed children — but IMAGES stay inline in
the richtext `body` (the skeleton lift did not separate them into media units;
pulling every <img> to a DAM weakref needs the DOM at extract time — the
extract_content semantic-mode rewrite). Net: real archetypes + editable
title/body/cta + typed children + tree-driven nav, vs 40 skeleton types.

Usage: semanticize_content.py <project> [--manifest PATH] [--out PATH]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup  # noqa: E402

_HEADING = ["h1", "h2", "h3", "h4"]

# Source-framework artifacts have NO place in contributed content: astro island
# wrappers/slots are unwrapped (keeping their children), astro/framework state
# scripts are dropped, and data-astro-*/framework attrs are stripped from every
# element. Editors must see clean semantic HTML, not transcription debris —
# and the debris is what kept re-hydrating the source SPA chrome.
_JUNK_UNWRAP = ("astro-island", "astro-slot")
_JUNK_DROP = ("astro-dev-toolbar", "template", "script", "noscript")


def _clean_html(html):
    """Strip framework transcription artifacts from a content HTML string."""
    if not html or "<" not in html:
        return html
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_JUNK_DROP):
        tag.decompose()
    for tag in soup.find_all(_JUNK_UNWRAP):
        tag.unwrap()
    for tag in soup.find_all(True):
        for attr in [a for a in tag.attrs
                     if a.startswith("data-astro") or a in ("renderer-url", "uid",
                                                            "client", "opts", "props",
                                                            "component-url", "component-export")]:
            del tag.attrs[attr]
    return "".join(str(c) for c in (soup.body.children if soup.body else [])).strip()


def _node_field_surface(manifest):
    """nodeType -> {'title':bool, 'body':bool, 'media':bool, 'cta':bool, 'child':nodeType|None,
    'childSurface':{...}}. Derived from the archetype component's supertypes/fields."""
    surf = {}
    mixns = manifest.get("mixns", "nsmix")

    def one(c):
        sup = c.get("supertypes") or []
        fields = {f["name"] for f in (c.get("fields") or [])}
        return {
            "title": "mix:title" in sup,
            "body": "body" in fields,
            "media": f"{mixns}:media" in sup,
            "cta": f"{mixns}:cta" in sup,
        }

    for c in (manifest.get("components", []) or []) + (manifest.get("crossCutting", []) or []):
        s = one(c)
        child = c.get("childType")
        if isinstance(child, dict) and child.get("nodeType"):
            csup = child.get("supertypes") or []
            cfields = {f["name"] for f in (child.get("fields") or [])}
            s["child"] = child["nodeType"]
            s["childSurface"] = {"title": "mix:title" in csup, "body": "body" in cfields,
                                 "media": f"{mixns}:media" in csup, "cta": f"{mixns}:cta" in csup}
        surf[c["nodeType"]] = s
    return surf


def _split_title_body(fields):
    """Join the lifted body* runs, pull the FIRST heading text out as the title,
    return (title, body_html_without_that_heading)."""
    runs = [fields[k] for k in sorted(fields, key=lambda k: (len(k), k))
            if k.startswith("body") and isinstance(fields[k], str)]
    html = "\n".join(runs).strip()
    if not html:
        # non-body lifted text (e.g. a plain 'title' or 'label' field)
        return (fields.get("title") or fields.get("label") or "").strip(), ""
    soup = BeautifulSoup(html, "lxml")
    title = ""
    for tag in _HEADING:
        h = soup.find(tag)
        if h and h.get_text(strip=True):
            title = h.get_text(" ", strip=True)
            h.decompose()          # remove the heading from the body
            break
    if not title:
        title = (fields.get("title") or "").strip()
    body = "".join(str(c) for c in (soup.body.children if soup.body else [])).strip()
    return title[:250], body


def _split_skeleton(skeleton):
    """Fallback title/body from the instance's SKELETON markup (used when the
    lift produced no body runs — observed: whole sections promoted with empty
    fields but a full skeleton). {{child:N}} markers are removed (children are
    separate instances) and the markup is cleaned of framework artifacts."""
    html = _clean_html(re.sub(r"\{\{child:\d+\}\}", "", skeleton or ""))
    if not html:
        return "", ""
    soup = BeautifulSoup(html, "lxml")
    title = ""
    for tag in _HEADING:
        h = soup.find(tag)
        if h and h.get_text(strip=True):
            title = h.get_text(" ", strip=True)
            h.decompose()
            break
    body = "".join(str(c) for c in (soup.body.children if soup.body else [])).strip()
    return title[:250], body


def _first_heading_text(html):
    """First heading's text — a COPY for jcr:title (the heading itself STAYS in
    the markup/body: the hybrid fidelity render needs it in place)."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in _HEADING:
        h = soup.find(tag)
        if h and h.get_text(strip=True):
            return h.get_text(" ", strip=True)[:250]
    return ""


def _mark_title_in_skeleton(skeleton, title):
    """Replace the first heading's TEXT with the {{f:title}} marker (jcr:title
    in nodePayload) so EDITING jcr:title reflows into the fidelity render —
    the roundtrip gate proved a plain copy leaves jcr:title a dead field. Only
    swaps when the heading text matches the lifted title (same source)."""
    if not skeleton or not title:
        return skeleton
    soup = BeautifulSoup(skeleton, "lxml")
    for tag in _HEADING:
        h = soup.find(tag)
        if h and h.get_text(strip=True):
            if h.get_text(" ", strip=True)[:250] == title:
                h.clear()
                h.append("{{f:title}}")
                return "".join(str(c) for c in
                               (soup.body.children if soup.body else [])).strip()
            break
    return skeleton


def _decompose_repeats(skeleton, ns):
    """CONTRACT decomposition (2026-07-16): repetition inside a region becomes
    CHILD NODE TYPES, never flat fields on the parent. Detect the largest group
    of >=2 sibling elements sharing the same (tag, classes) signature with real
    content; each becomes a {ns}:cardItem child payload (title marked
    {{f:title}} in its own skeleton fragment, image -> DAM file when the src is
    a mirror asset); the parent skeleton gets {{child:N}} markers in place.
    Returns (new_skeleton, children[]) — ([], unchanged) when nothing repeats."""
    if not skeleton or "{{child:" in skeleton:
        return skeleton, []
    soup = BeautifulSoup(skeleton, "lxml")
    best, best_sig = [], None
    for parent in soup.find_all(True):
        groups = {}
        for el in parent.find_all(True, recursive=False):
            sig = (el.name, tuple(sorted(el.get("class") or [])))
            groups.setdefault(sig, []).append(el)
        for sig, els in groups.items():
            if len(els) >= 2 and len(els) > len(best) and sig[1]:
                # real content units, not styling wrappers
                if all(len(e.get_text(" ", strip=True)) >= 10 or e.find("img") for e in els):
                    best, best_sig = els, sig
    if len(best) < 2:
        return skeleton, []
    children = []
    for i, el in enumerate(best):
        frag = str(el)
        title = _first_heading_text(frag)
        ch = {"type": "cardItem", "nodeType": f"{ns}:cardItem", "promoted": True,
              "fields": {}, "skeleton": _mark_title_in_skeleton(frag, title) if title else frag}
        if title:
            ch["fields"]["title"] = title
        img = el.find("img")
        src = (img.get("src") or "") if img else ""
        mfile = os.path.basename(src.split("?")[0])
        if img and re.match(r"^[a-f0-9]{12,}\.\w{2,4}$", mfile):
            ch["media"] = [{"name": "image", "file": mfile,
                            "orig": str(img)[:20000]}]
        marker = soup.new_string("{{child:%d}}" % i)
        el.replace_with(marker)
        children.append(ch)
    new_sk = "".join(str(c) for c in (soup.body.children if soup.body else [])).strip()
    return new_sk, children


def _semanticize_instance(inst, node, surf):
    """HYBRID (Option B, 2026-07-15): the archetype TYPE system provides the
    authoring surface (mix:title, contrib slots, media/cta mixins) while the
    node's own captured SKELETON markup provides the pixel-faithful default
    render. So this keeps the ORIGINAL lifted payload (field runs, media, link,
    skeleton with {{f:}}/{{child:N}} markers intact — the loader's promoted_props
    slots every field onto the node) and only:
      - cleans framework junk out of every HTML value,
      - COPIES the first heading into a `title` field (jcr:title for jContent
        lists + nav; the heading stays in the markup — never extracted),
      - recurses into embedded children."""
    out = dict(inst)
    out["promoted"] = True
    fields = dict(inst.get("fields") or {})
    for k, v in list(fields.items()):
        if isinstance(v, str) and "<" in v:
            fields[k] = _clean_html(v)
        # no empty-string keys: the loader skips them but the editor-surface
        # gate counts KEYS — an '' field is a phantom form expectation
        if isinstance(fields.get(k), str) and not fields[k].strip():
            del fields[k]
    if inst.get("skeleton"):
        out["skeleton"] = _clean_html(inst["skeleton"])
    if not fields.get("title"):
        # jcr:title must be a LIVE field, not a dead copy (roundtrip gate):
        # 1) heading inside a body RUN -> restructure: the heading element moves
        #    into the skeleton as <hN>{{f:title}}</hN> before that run's marker,
        #    its text becomes the title field, the body value loses the heading.
        #    Same rendered bytes when unedited; BOTH title and body edits reflow.
        # 2) heading inline in the skeleton -> its text becomes {{f:title}}.
        sk = out.get("skeleton") or ""
        for k in sorted((k for k, v in fields.items()
                         if k.startswith("body") and isinstance(v, str) and "<" in v),
                        key=lambda k: (len(k), k)):
            soup = BeautifulSoup(fields[k], "lxml")
            h = next((soup.find(t) for t in _HEADING if soup.find(t)), None)
            if h is None or not h.get_text(strip=True):
                continue
            t = h.get_text(" ", strip=True)[:250]
            marker = "{{f:%s}}" % k
            # only restructure when the heading LEADS the run — moving a
            # mid-run heading in front of the marker would reorder content
            first_el = next((c for c in (soup.body.children if soup.body else [])
                             if getattr(c, "name", None)), None)
            if first_el is not h:
                fields["title"] = t
                break
            if sk and marker in sk:
                h_marked = BeautifulSoup(str(h), "lxml").find(h.name)
                h_marked.clear()
                h_marked.append("{{f:title}}")
                out["skeleton"] = sk.replace(marker, str(h_marked) + marker, 1)
                h.decompose()
                rest = "".join(str(c) for c in
                               (soup.body.children if soup.body else [])).strip()
                if rest:
                    fields[k] = rest
                else:
                    # the run WAS the heading: no empty '' key left behind
                    # (the editor-surface gate counts keys, the loader skips
                    # empty values — an '' body is a phantom expectation)
                    del fields[k]
            fields["title"] = t
            break
        if not fields.get("title"):
            t = _first_heading_text(sk)
            if t:
                out["skeleton"] = _mark_title_in_skeleton(sk, t)
                fields["title"] = t
    # CONTRACT: ONE body per node. Runs 2+ are inlined VERBATIM into the
    # skeleton at their own marker positions (fidelity keeps every run in
    # place); the payload keeps only `body`. Real repetition becomes children
    # in the main loop's decomposition pass.
    sk = out.get("skeleton") or ""
    for k in sorted((k for k in fields if re.match(r"body\d+$", k)),
                    key=lambda k: (len(k), k)):
        v = fields.pop(k)
        if sk and ("{{f:%s}}" % k) in sk:
            sk = sk.replace("{{f:%s}}" % k, v if isinstance(v, str) else "", 1)
        elif isinstance(v, str) and v.strip():
            # no marker home: append after body's marker so nothing is lost
            anchor = "{{f:body}}"
            sk = sk.replace(anchor, anchor + v, 1) if anchor in sk else sk + v
    if sk:
        out["skeleton"] = sk
    # CONTRACT: the payload may only carry fields the TYPE declares — the
    # numbered contrib mixins are gone, so anything else stays INLINE in the
    # markup (fidelity keeps it; it is editable as part of a body/child, not as
    # a phantom field). Observed live: 'body' on cardGrid, 'label', image2Orig
    # all failed "Couldn't find definition for property".
    s = surf.get(node) or {}
    sk2 = out.get("skeleton") or ""

    def inline(k, v):
        nonlocal sk2
        marker = "{{f:%s}}" % k
        if marker in sk2:
            sk2 = sk2.replace(marker, v if isinstance(v, str) else "", 1)

    # labels (all of them): no type declares label fields
    for k in sorted((k for k in fields if re.match(r"label\d*$", k)),
                    key=lambda k: (len(k), k)):
        inline(k, fields.pop(k))
    # body on a type whose surface has no body (cardGrid, ctaSection, chrome)
    if fields.get("body") and not s.get("body"):
        inline("body", fields.pop("body"))
    # media: ONE weakref unit max (the {mixns}:media/contribImage slot); the
    # markup of further units replaces their {{media:*}} markers verbatim
    media = inst.get("media") or []
    if media:
        keep, rest = media[0], media[1:]
        out["media"] = [{**keep, "name": "image"}]
        for mu in rest:
            mk = "{{media:%s}}" % mu.get("name", "")
            if mk in sk2:
                sk2 = sk2.replace(mk, _clean_html(mu.get("orig") or ""), 1)
    if sk2:
        out["skeleton"] = sk2
    out["fields"] = fields
    # embedded typed children -> same hybrid treatment
    child_node = (surf.get(node) or {}).get("child")
    if inst.get("children"):
        out["children"] = [_semanticize_instance(
            {**ch, "type": ch.get("type") or child_node or inst["type"]},
            ch.get("type") or child_node, surf) for ch in inst["children"]]
    # CONTRACT: repetition inside the region -> {ns}:cardItem CHILDREN (never
    # flat parent fields); the lifted link -> a {ns}:cta CHILD (never a mixin)
    ns = (node or "x:y").split(":")[0]
    if not out.get("children") and out.get("skeleton"):
        new_sk, kids = _decompose_repeats(out["skeleton"], ns)
        if kids:
            out["skeleton"] = new_sk
            out["children"] = kids
    if inst.get("link"):
        cta = {"type": "cta", "nodeType": f"{ns}:cta", "promoted": True,
               "fields": {}, "link": inst["link"]}
        lbl = inst.get("linkLabel") or (inst.get("fields") or {}).get("label")
        if lbl:
            cta["fields"]["linkLabel"] = str(lbl)[:250]
            cta["linkLabel"] = str(lbl)[:250]
        out.pop("link", None)
        out.setdefault("children", []).append(cta)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--manifest")
    ap.add_argument("--out")
    a = ap.parse_args()
    load_p = f"orchestration/content/{a.project}.content-load.json"
    man_p = a.manifest or f"projects/{a.project}/workflow-output/component-manifest.json"
    data = json.load(open(load_p))
    manifest = json.load(open(man_p))
    if manifest.get("model") != "archetype":
        sys.exit("FAIL: manifest is not the archetype model — run segment2manifest --archetypes")
    itm = {k.lower(): v for k, v in (manifest.get("instanceTypeMap") or {}).items()}
    surf = _node_field_surface(manifest)
    passthrough = manifest.get("passthroughType")
    # archetype container/child lookups for the library-instance remap
    child_of = {c["nodeType"]: c["childType"]["nodeType"]
                for c in (manifest.get("components") or [])
                if isinstance(c.get("childType"), dict) and c["childType"].get("nodeType")}
    grid_nt = (next((c["nodeType"] for c in (manifest.get("components") or [])
                     if c.get("archetype") == "cardGrid"), None)
               or next(iter(child_of), None))  # any container that HAS a childType

    # The skeleton content-load carries a large passthrough tail (whitespace,
    # wrapper markup, chrome fragments) needed for BYTE fidelity — the semantic
    # model does not want those as rawHtml editor nodes. DROP passthrough with no
    # real visible text; keep only substantial uncovered content (>= MIN_VIS
    # visible chars) as rawHtml. Dropping shifts indices, so parents are remapped
    # (a semantic section whose wrapper is dropped becomes a top-level page node).
    MIN_VIS = 24

    def _visible(html):
        if not html or "<" not in html:
            return re.sub(r"\s+", " ", (html or "")).strip()
        soup = BeautifulSoup(html, "lxml")
        for el in soup.find_all(["script", "style", "noscript", "template"]):
            el.extract()
        return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()

    n_sem = n_pass = n_drop = 0
    for page in data.get("pages", {}).values():
        # ARCHETYPE model: the fidelity `shell` spec (full source body around
        # <main> — nav/cookie-consent/notification chrome + SPA state) is NOT
        # used by the semantic Layout and must not become a 100KB rawHtml blob
        # node editors see in jContent. Drop it; the Layout falls back to the
        # css-manifest for source styling (scripts intentionally excluded).
        page.pop("shell", None)
        transformed = []                       # (keep: bool, instance | None)
        for inst in page.get("instances", []):
            if inst.get("area"):
                # ARCHETYPE model: captured source chrome (rawHtml routed to an
                # absolute area — the source's own header/nav/footer markup with
                # its SPA islands) is REPLACED by contributed Jahia chrome
                # (build_nav_tree places mainNavigation/siteHeader/footer), so
                # passthrough-typed area captures are dropped. A semantic-typed
                # area singleton (none today) would still pass through.
                node = itm.get((inst.get("type") or "").lower())
                if node is None or node == passthrough:
                    transformed.append((False, None))
                    n_drop += 1
                else:
                    transformed.append((True, inst))
                continue
            node = itm.get((inst.get("type") or "").lower())
            # LIBRARY instances (P2.5): containers with a libraryPlan and their
            # typed atoms (own nodeType, structured atomTitle/href/imageFile)
            # are created natively by load_content's library path as REAL typed
            # nodes — exactly the semantic model for card grids. Pass them
            # through intact (losing these keys is what gutted the content),
            # only cleaning embedded markup of framework artifacts.
            if inst.get("libraryAtom") or inst.get("libraryPlan"):
                for k in ("imgOrig", "skeleton", "skeletonOrig"):
                    if inst.get(k):
                        inst[k] = _clean_html(inst[k])
                for k, v in list((inst.get("fields") or {}).items()):
                    if isinstance(v, str) and "<" in v:
                        inst["fields"][k] = _clean_html(v)
                # remap SKELETON-era library nodeTypes (sgp:card/logoWall/…)
                # onto the deployed ARCHETYPE set: containers via the instance
                # type map (fallback: the cardGrid archetype), atoms via the
                # mapped container's manifest childType. Unknown node types
                # were the #1 library-create failure (observed live).
                if inst.get("libraryPlan"):
                    inst["nodeType"] = (itm.get((inst.get("type") or "").lower())
                                        or grid_nt or inst.get("nodeType"))
                    # the container's OWN text (heading + inline markup around
                    # the {{child}} markers — the hero lived there) is invisible
                    # to the semantic views inside the skeleton prop: surface it
                    # as title/body fields so the archetype view renders it.
                    f = inst.setdefault("fields", {})
                    # contract: undeclared fields inline back into the skeleton
                    # at their markers (extract lifts runs OUT with {{f:*}});
                    # the container renders from its skeleton either way
                    sflib = surf.get(inst.get("nodeType")) or {}
                    sk_l = inst.get("skeleton") or ""
                    for k in [k for k in sorted(f, key=lambda k: (len(k), k))
                              if re.match(r"(body|label)\d*$", k)]:
                        if k == "body" and sflib.get("body"):
                            continue
                        v = f.pop(k)
                        if ("{{f:%s}}" % k) in sk_l:
                            sk_l = sk_l.replace("{{f:%s}}" % k,
                                                v if isinstance(v, str) else "", 1)
                    if sk_l:
                        inst["skeleton"] = sk_l
                    if not f.get("title") and not f.get("body") and inst.get("skeleton"):
                        t, b = _split_skeleton(inst["skeleton"])
                        if t:
                            f["title"] = t
                        # body only when the mapped TYPE declares it (contract:
                        # payload fields must have a home; the container's
                        # markup renders from its skeleton regardless)
                        if b and len(_visible(b)) >= MIN_VIS \
                                and (surf.get(inst.get("nodeType")) or {}).get("body"):
                            f["body"] = b
                elif inst.get("libraryAtom"):
                    # CONTRACT: all repeatable items are the ONE reusable
                    # {ns}:cardItem child type (typed by anatomy, not by parent)
                    ns_ = (passthrough or "x:y").split(":")[0]
                    inst["nodeType"] = f"{ns_}:cardItem"
                transformed.append((True, inst))
                n_sem += 1
                continue
            typed = (inst.get("promoted") or inst.get("skeleton")) and node and node != passthrough
            if typed:
                transformed.append((True, _semanticize_instance(inst, node, surf)))
                n_sem += 1
                continue
            # untyped: keep substantial verbatim content (fields.html, or for a
            # promoted passthrough WRAPPER its skeleton minus {{child}} markers —
            # inline markup between markers is real content, dropping it lost
            # the hero). Whitespace/chrome fragments still drop below MIN_VIS.
            html = (inst.get("fields") or {}).get("html", "")
            if not _visible(html) and inst.get("skeleton"):
                html = re.sub(r"\{\{child:\d+\}\}", "", inst["skeleton"])
            html = _clean_html(html) if html else ""
            if len(_visible(html)) >= MIN_VIS:
                transformed.append((True, {"type": "rawHtml", "passthrough": True,
                                           "fields": {"html": html}}))
                n_pass += 1
            else:
                transformed.append((False, None))         # whitespace/markup/chrome — DROP
                n_drop += 1
        # compact + remap parent indices (dropped parent -> top-level)
        remap, kept = {}, []
        for oldi, (keep, ins) in enumerate(transformed):
            if keep:
                remap[oldi] = len(kept)
                kept.append(ins)
        for ins in kept:
            if ins.get("parent") is not None:
                ins["parent"] = remap.get(ins["parent"])   # None if the wrapper was dropped
                # a rawHtml passthrough declares no child nodes — a typed child
                # nesting under it is a guaranteed ConstraintViolation (observed
                # live); it becomes a top-level sibling instead.
                if ins["parent"] is not None and kept[ins["parent"]].get("passthrough"):
                    ins["parent"] = None
        page["instances"] = kept

    data["adapter"] = "semantic"
    data["model"] = "archetype"
    out = a.out or load_p
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print(f"[semanticize_content] {out}: {n_sem} semantic instance(s), "
          f"{n_pass} passthrough, over {len(data.get('pages', {}))} page(s)")


if __name__ == "__main__":
    main()
