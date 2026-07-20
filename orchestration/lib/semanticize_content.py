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


def _distill_classmap(skeleton):
    """MANDATE (2026-07-16): views must wear the ORIGINAL site's classes so the
    already-linked source CSS styles the Jahia-rendered markup. Distill the
    source class names from the node's structure markup: root element, first
    heading, first image, first link/button, and the repeating-item signature.
    Stored as a hidden JSON prop; resolveSemantic feeds it to the views."""
    if not skeleton:
        return None
    soup = BeautifulSoup(skeleton, "lxml")
    root = next((c for c in (soup.body.children if soup.body else [])
                 if getattr(c, "name", None)), None)
    if root is None:
        return None
    cm = {}

    def cls(el):
        return " ".join(el.get("class") or []) if el is not None else ""

    cm["root"] = cls(root)
    h = next((x for t in ("h1", "h2", "h3", "h4", "h5", "h6")
              for x in [root.find(t)] if x is not None), None)
    cm["title"] = cls(h)
    cm["image"] = cls(root.find("img"))
    cm["link"] = cls(root.find("a"))
    # the wrapper that holds the {{child:N}} markers = the items row/track
    marker_parent = None
    for el in root.find_all(True):
        if any("{{child:" in str(x) for x in el.children if not getattr(x, "name", None)):
            marker_parent = el
            break
    cm["items"] = cls(marker_parent)
    cm = {k: v for k, v in cm.items() if v}
    return json.dumps(cm, ensure_ascii=False) if cm else None


def _sweep_text_to_body(sk, fields, min_chars=60, children_out=None, ns=None):
    """Selective authorability sweep: maximal text-bearing elements WITHOUT any
    marker move into the body field; marker-bearing structure stays."""
    resid = re.sub(r"\{\{[^}]+\}\}", " ", sk or "")
    resid = re.sub(r"<[^>]+>", " ", resid)
    if not sk or len(re.sub(r"\s+", " ", resid).strip()) < min_chars:
        return sk
    soup = BeautifulSoup(sk, "lxml")
    # CHROME DEBRIS (2026-07-17, gate-caught): breadcrumb fragments leak into
    # captured regions and would sweep into body as fake content ('Receiving
    # Help & Support'). Chrome is replaced by design — DELETE, never move.
    for _el in soup.find_all(True, class_=lambda c: c and "breadcrumb" in " ".join(c).lower()):
        _el.decompose()
    for _el in soup.find_all(True, attrs={"aria-label": re.compile("breadcrumb", re.I)}):
        _el.decompose()
    moved, taken = [], []
    for el in (soup.body.find_all(True) if soup.body else []):
        s_el = str(el)
        if "{{" in s_el:
            continue
        if any(el in t.descendants for t in taken):
            continue
        if len(el.get_text(" ", strip=True)) >= 20:
            moved.append(s_el)
            taken.append(el)
    # PARENT-GROUPED slots (2026-07-20, home hero +331px): sweeping elements
    # from DIFFERENT wrappers into ONE body rips them out of their grid cells
    # (the Track-panel header merged into the left column's body, rendered as
    # a second grid item, and pushed the blue card to a new grid row). Each
    # distinct PARENT gets its own slot — the first group is body, later
    # groups become body2, body3… — and every slot's marker replaces its
    # group's first node IN PLACE, so each fragment renders where it lived.
    # (2026-07-17 in-place rule preserved: never tail-append a marker.)
    _body_taken = "{{f:body}}" in sk
    taken_ids = set(map(id, taken))
    groups, gindex = [], {}
    for el in taken:
        key = id(el.parent)
        if key not in gindex:
            gindex[key] = {"parts": []}
            groups.append(gindex[key])
        gindex[key]["parts"].append(("el", el))
    # LOOSE TEXT NODES (the named-debt hoarders): text sitting directly under
    # a marker-bearing wrapper is invisible to the element mover — wrap+move it
    for tx in list(soup.body.strings if soup.body else []):
        t_s = str(tx)
        if "{{" in t_s or len(t_s.strip()) < 20:
            continue
        if any(id(a) in taken_ids for a in tx.parents):
            continue  # inside a taken element — moves with its group
        key = id(tx.parent)
        if key not in gindex:
            gindex[key] = {"parts": []}
            groups.append(gindex[key])
        gindex[key]["parts"].append(("tx", tx))
    moved_any = False
    slot_n = 1
    for gi, g in enumerate(groups):
        if children_out is not None and gi >= 4:
            # OVER-FRAGMENTATION producer fix (gate 2026-07-20: editors saw
            # Text(2)..Text(23)): groups beyond the 4th become cardItem
            # CHILDREN — each an editable component spliced at its position
            # via {{child:N}}, not another wall-of-text slot.
            idx = len(children_out)
            parts, first = [], True
            for kind, node in g["parts"]:
                parts.append(str(node) if kind == "el" else f"<p>{str(node).strip()}</p>")
                if first:
                    node.replace_with(soup.new_string("{{child:%d}}" % idx))
                    first = False
                else:
                    node.extract()
            children_out.append({
                "type": "cardItem",
                "nodeType": f"{ns}:cardItem" if ns else None,
                "promoted": True,
                "fields": {"body": "\n".join(p for p in parts if p.strip()).strip()},
                "skeleton": "{{f:body}}"})
            moved_any = True
            continue
        if gi == 0:
            name = "body"
        else:
            slot_n += 1
            while f"body{slot_n}" in fields:
                slot_n += 1
            name = f"body{slot_n}"
        marker = "{{f:%s}}" % name
        placed = (name == "body" and _body_taken) or (marker in sk)
        parts = []
        for kind, node in g["parts"]:
            parts.append(str(node) if kind == "el" else f"<p>{str(node).strip()}</p>")
            if not placed:
                node.replace_with(soup.new_string(marker))
                placed = True
            else:
                node.extract()
        if name == "body":
            _body_taken = True
        val = "\n".join(x for x in parts if x and x.strip()).strip()
        if val:
            fields[name] = "\n".join(
                x for x in [fields.get(name, ""), val] if x).strip()
            moved_any = True
    if moved_any:
        sk = "".join(str(c) for c in soup.body.children).strip()
        if fields.get("body") and "{{f:body}}" not in sk:
            sk += "{{f:body}}"   # nothing replaced in place (edge) — keep tail fallback
    return sk


def _decompose_repeats(skeleton, ns, media_units=None, parent_fields=None):
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
                if all(len(e.get_text(" ", strip=True)) >= 10 or e.find("img")
                       or "{{media:" in str(e) for e in els):
                    best, best_sig = els, sig
    if len(best) < 2:
        return skeleton, []
    children = []
    for i, el in enumerate(best):
        frag = str(el)
        title = _first_heading_text(frag)
        ch = {"type": "cardItem", "nodeType": f"{ns}:cardItem", "promoted": True,
              "fields": {}, "skeleton": _mark_title_in_skeleton(frag, title) if title else frag}
        # MARKER RELOCATION (2026-07-20, delivery-rates nested cards): a
        # {{f:bodyN}}/{{f:labelN}} marker carved into this fragment must bring
        # its parent-level VALUE along — the marker rendered a HOLE while the
        # value sat unreachable on the parent (same family as the link-shell
        # class). Values already merged away are untraceable: drop the marker
        # (the content lives in the parent body; an empty hole helps nobody).
        # The reconcile pairing gate keeps catching NEW leaks.
        if parent_fields:
            for mk in set(re.findall(r"\{\{f:(body\d+|label\d*)\}\}", ch["skeleton"])):
                if mk in parent_fields and mk not in ch["fields"]:
                    ch["fields"][mk] = parent_fields.pop(mk)
        ch["skeleton"] = re.sub(
            r"\{\{f:(body\d+|label\d*)\}\}",
            lambda m: m.group(0) if m.group(1) in ch["fields"] else "",
            ch["skeleton"])
        ch["skeleton"] = _sweep_text_to_body(ch["skeleton"], ch["fields"], min_chars=40)
        cm = _distill_classmap(ch["skeleton"])
        if cm:
            ch["classMap"] = cm
        if title:
            ch["fields"]["title"] = title
        img = el.find("img")
        src = (img.get("src") or "") if img else ""
        mfile = os.path.basename(src.split("?")[0])
        if img and re.match(r"^[a-f0-9]{12,}\.\w{2,4}$", mfile):
            ch["media"] = [{"name": "image", "file": mfile,
                            "orig": str(img)[:20000]}]
        # slides whose <img> was lifted to a {{media:*}} marker at extract:
        # claim the parent's media UNIT so the slide owns its image (weakref
        # + imgOrig) and the marker resolves INSIDE the track via RenderChild
        if not ch.get("media") and media_units:
            mm = re.findall(r"\{\{media:([^}]+)\}\}", ch["skeleton"])
            if mm:
                unit = next((u for u in media_units if u.get("name") == mm[0]), None)
                if unit is not None:
                    media_units.remove(unit)
                    ch["media"] = [{**unit, "name": "image"}]
                    ch["skeleton"] = ch["skeleton"].replace(
                        "{{media:%s}}" % mm[0], "{{media:image}}", 1)
                for name in mm[1:]:
                    u2 = next((u for u in media_units if u.get("name") == name), None)
                    if u2 is not None:
                        media_units.remove(u2)
                        ch["skeleton"] = ch["skeleton"].replace(
                            "{{media:%s}}" % name, u2.get("orig") or "", 1)
        marker = soup.new_string("{{child:%d}}" % i)
        el.replace_with(marker)
        children.append(ch)
    new_sk = "".join(str(c) for c in (soup.body.children if soup.body else [])).strip()
    return new_sk, children


def _itemize_fragment(frag):
    """Turn an item's markup fragment into (skeleton, title, body): first
    heading's text -> {{f:title}}, the content AFTER it (within its parent) ->
    ONE {{f:body}} whose value is the extracted richtext. Editing title/body in
    Content Editor then reflows into the fidelity render (the whole point:
    what you see rendered must be what you edit)."""
    if not frag:
        return frag, "", ""
    soup = BeautifulSoup(frag, "lxml")
    title = body = ""
    h = next((x for t in ("h1", "h2", "h3", "h4", "h5", "h6")
              for x in [soup.find(t)] if x is not None), None)
    if h is not None and h.get_text(strip=True):
        title = h.get_text(" ", strip=True)[:250]
        h.clear()
        h.append("{{f:title}}")
        sibs = list(h.next_siblings)
        parts = [str(x) for x in sibs if str(x).strip()]
        if parts:
            body = "".join(parts).strip()
            for x in sibs:
                x.extract()
            h.insert_after("{{f:body}}")
    else:
        # no heading: the whole item content becomes ONE editable richtext —
        # guaranteed editability beats perfect structure (display-not-editable
        # gate). The root element travels INSIDE the body (2026-07-20: an
        # unwrapped root dropped the sizing classes and a viewBox-only svg
        # icon exploded to container width — delivery-rates tabs).
        root = next((c for c in (soup.body.children if soup.body else [])
                     if getattr(c, "name", None)), None)
        if root is not None and root.get_text(strip=True):
            body = str(root).strip()
            root.replace_with(soup.new_string("{{f:body}}"))
    sk = "".join(str(c) for c in (soup.body.children if soup.body else [])).strip()
    return sk, title, body


def _decompose_library(transformed, ns):
    """CONTRACT pass for LIBRARY containers: their skeletons embed item markup
    VERBATIM (no {{child:N}}), so items rendered from the parent were neither
    selectable in Page Builder nor showing their text in Content Editor (the
    2026-07-16 finding). Replace each atom's fragment in the container skeleton
    with {{child:N}} and give the atom its own skeleton + title/body fields."""
    swapped = 0
    for p_idx, (keep, parent) in enumerate(transformed):
        if not keep or not parent or not parent.get("libraryPlan"):
            continue
        sk = parent.get("skeleton") or ""
        atoms = [(i, a) for i, (k, a) in enumerate(transformed)
                 if k and a and a.get("libraryAtom") and a.get("parent") == p_idx]
        for n, (a_idx, atom) in enumerate(atoms):
            frag = _clean_html(atom.get("imgOrig") or "")
            if not frag:
                continue
            item_sk, t, b = _itemize_fragment(frag)
            atom["skeleton"] = _sweep_text_to_body(item_sk, atom.setdefault("fields", {}),
                                                    min_chars=40)
            item_sk = atom["skeleton"]
            cm = _distill_classmap(item_sk)
            if cm:
                atom["classMap"] = cm
            f = atom.setdefault("fields", {})
            if t and not f.get("title"):
                f["title"] = t
            if b and not f.get("body"):
                f["body"] = b
            # PREFER the imageFile-anchored WRAPPER swap: the imgOrig fragment
            # is often just the <img> tag — substring-swapping it orphans the
            # slide wrapper and its LABEL in the plan (enterprise hero quick
            # links, 80-char leftovers). The bare-fragment path is the fallback.
            if atom.get("imageFile") and atom["imageFile"] in sk:
                # SERIALIZATION DRIFT (2026-07-17): the atom's imgOrig fragment
                # rarely substring-matches the plan skeleton (attribute order /
                # cleaning differences), so slides stayed verbatim, the sweep
                # flattened them into body, and atoms never created (careers
                # culture: 5175px of stacked photos). Locate the slide by its
                # UNIQUE imageFile hash and replace the repeating slide WRAPPER
                # (the ancestor whose class-signature repeats among siblings).
                soup_sk = BeautifulSoup(sk, "lxml")
                img_el = soup_sk.find("img", src=lambda v: bool(v) and atom["imageFile"] in v)
                if img_el is None:
                    continue
                el, best_el = img_el, None
                while el.parent is not None and getattr(el.parent, "name", None) not in (None, "[document]", "body", "html"):
                    sig = (el.name, tuple(sorted(el.get("class") or [])))
                    same = [x for x in el.parent.find_all(True, recursive=False)
                            if (x.name, tuple(sorted(x.get("class") or []))) == sig]
                    if len(same) >= 2 and sig[1]:
                        best_el = el          # OUTERMOST repeating level wins:
                    el = el.parent            # the icon div repeats too, but the
                el = best_el or img_el        # full link item carries the LABEL
                slide_html = str(el)
                # the slide wrapper becomes the atom's OWN skeleton (keeps the
                # track cell classes); its image renders via the atom weakref
                atom["skeleton"] = _sweep_text_to_body(
                    _clean_html(slide_html), atom.setdefault("fields", {}), min_chars=40)
                _lbl = BeautifulSoup(slide_html, "lxml").get_text(" ", strip=True)
                if _lbl and len(_lbl) <= 80 and not atom["fields"].get("title"):
                    atom["fields"]["title"] = _lbl   # rule 24: the label is editable
                cm2 = _distill_classmap(atom["skeleton"])
                if cm2:
                    atom["classMap"] = cm2
                el.replace_with(soup_sk.new_string("{{child:%d}}" % n))
                sk = "".join(str(c) for c in (soup_sk.body.children if soup_sk.body else [])).strip()
                swapped += 1
            elif frag and frag in sk:
                sk = sk.replace(frag, "{{child:%d}}" % n, 1)
                swapped += 1
        parent["skeleton"] = _sweep_text_to_body(sk, parent.setdefault("fields", {}))
        cm3 = _distill_classmap(parent["skeleton"])
        if cm3:
            parent["classMap"] = cm3
    return swapped


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
    # GALLERY/CAROUSEL decomposition MUST precede the extra-media merge: the
    # slides carry {{media:*}} markers (extract lifted their <img>), so the
    # merge would inline media[1..] into body — flattening a 5-slide track
    # into stacked full-width images (careers culture section, 5175px vs the
    # source's one-row track; found 2026-07-17). Decomposed slides claim
    # their media units; only UNCLAIMED media reach the merge below.
    _dns = (node or "x:y").split(":")[0]
    if not inst.get("children") and out.get("skeleton"):
        _sk2, _kids = _decompose_repeats(out["skeleton"], _dns, inst.get("media"),
                                         parent_fields=fields)
        if _kids:
            out["skeleton"] = _sk2
            out["children"] = _kids
    # CONTRACT v2 (2026-07-16): authorable content lives in PROPERTIES, never
    # in the hidden skeleton. Every type owns ONE body richtext — text runs 2+,
    # label runs and extra media all MERGE INTO the body VALUE; their markers
    # collapse into the single {{f:body}} slot. Skeleton = structure only.
    sk = out.get("skeleton") or ""
    body_parts = [fields.get("body")] if isinstance(fields.get("body"), str) else []
    _merge_marker_placed = "{{f:body}}" in sk

    # STRUCTURE-AWARE MERGE (2026-07-20, home hero +331px): folding a run
    # whose marker lives in a DIFFERENT wrapper than the body slot rips it out
    # of its grid cell — the Track-panel header merged into the left column's
    # body, became a second grid item, and pushed the card to a new grid row.
    # A run only merges when its marker shares the body marker's PARENT
    # element; otherwise it keeps its own bodyN/labelN slot (the whole chain
    # supports them: cnd_emit contribBody/LabelN, loader slot, renderer
    # {{f:bodyN}} splice).
    def _marker_parent_sig(marker, sk_html):
        if marker not in sk_html:
            return None
        try:
            soup_mk = BeautifulSoup(sk_html, "lxml")
            t = soup_mk.find(string=lambda s: s and marker in s)
            if t is None or t.parent is None:
                return None
            p = t.parent
            return (p.name, tuple(p.get("class") or []),
                    sum(1 for _ in p.parents))
        except Exception:
            return None

    _anchor = _marker_parent_sig("{{f:body}}", sk)
    for k in sorted((k for k in fields if re.match(r"body\d+$", k)),
                    key=lambda k: (len(k), k)):
        marker = "{{f:%s}}" % k
        sig = _marker_parent_sig(marker, sk)
        if sig is not None and _merge_marker_placed and _anchor is not None \
                and sig != _anchor:
            continue  # different wrapper: stays its own editable slot
        v = fields.pop(k)
        if isinstance(v, str) and v.strip():
            body_parts.append(v)
        # IN-PLACE (2026-07-17, gate-caught): the first folded run's marker
        # becomes the {{f:body}} slot — tail-appending rendered the merged
        # body OUTSIDE the layout root
        if not _merge_marker_placed and marker in sk:
            sk = sk.replace(marker, "{{f:body}}", 1)
            _merge_marker_placed = True
            _anchor = _marker_parent_sig("{{f:body}}", sk)
        else:
            sk = sk.replace(marker, "", 1)
    for k in sorted((k for k in fields if re.match(r"label\d*$", k)),
                    key=lambda k: (len(k), k)):
        marker = "{{f:%s}}" % k
        sig = _marker_parent_sig(marker, sk)
        if sig is not None and _merge_marker_placed and _anchor is not None \
                and sig != _anchor:
            continue  # positioned label (business[7] {{f:label}} class)
        v = fields.pop(k)
        if isinstance(v, str) and v.strip():
            body_parts.append(f"<p>{v}</p>")
        sk = sk.replace(marker, "", 1)
    media = inst.get("media") or []
    if media:
        keep, rest = media[0], media[1:]
        out["media"] = [{**keep, "name": "image"}]
        for mu in rest:
            img_html = _clean_html(mu.get("orig") or "")
            if img_html:
                body_parts.append(img_html)
            sk = sk.replace("{{media:%s}}" % mu.get("name", ""), "", 1)
    merged = "\n".join(p for p in body_parts if p and p.strip()).strip()
    if merged:
        fields["body"] = merged
        if "{{f:body}}" not in sk and sk:
            sk += "{{f:body}}"
    # LAST-RESORT AUTHORABILITY: text the lift missed moves into body
    # (one editable field beats frozen markup); child markers keep their spots.
    resid = re.sub(r"\{\{[^}]+\}\}", " ", sk or "")
    resid = re.sub(r"<[^>]+>", " ", resid)
    if sk and len(re.sub(r"\s+", " ", resid).strip()) >= 60:
        soup2 = BeautifulSoup(sk, "lxml")
        if "{{child:" not in sk:
            # wholesale: inner content of the root becomes the body
            root2 = next((c for c in (soup2.body.children if soup2.body else [])
                          if getattr(c, "name", None)), None)
            if root2 is not None:
                inner = "".join(str(c) for c in root2.children).strip()
                inner = inner.replace("{{f:title}}", fields.get("title", ""))
                inner = re.sub(r"\{\{[^}]+\}\}", "", inner)
                fields["body"] = "\n".join(
                    x for x in [inner, fields.get("body", "")] if x).strip()
                root2.clear()
                root2.append("{{f:body}}")
                sk = "".join(str(c) for c in soup2.body.children).strip()
        else:
            # selective: shared sweep (elements AND loose text nodes without
            # markers move to body; marker-bearing structure stays in place).
            # Sweep-children only when the instance has none of its own (the
            # {{child:N}} indexes would collide with inst children otherwise).
            _sweep_kids = [] if not inst.get("children") else None
            sk = _sweep_text_to_body(sk, fields, min_chars=60,
                                     children_out=_sweep_kids,
                                     ns=(node or "x:y").split(":")[0])
            if _sweep_kids:
                out["children"] = _sweep_kids
    if sk:
        out["skeleton"] = sk
        cm = _distill_classmap(sk)
        if cm:
            out["classMap"] = cm
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
        new_sk, kids = _decompose_repeats(out["skeleton"], ns, parent_fields=fields)
        if kids:
            out["skeleton"] = new_sk
            out["children"] = kids
    if inst.get("link"):
        lbl = (inst.get("linkLabel") or (inst.get("fields") or {}).get("label")
               or (inst.get("fields") or {}).get("linkLabel")
               # whole-card anchors: the accessible name IS the card title
               or fields.get("title"))
        # ICON-ONLY links (2026-07-17, arrow anchors on cards): no label AND the
        # anchor still lives in the skeleton -> lifting it makes an EMPTY cta
        # DUPLICATE (gate: 'cta child carries no fields'). The skeleton anchor
        # renders the arrow faithfully; skip the lift.
        _href = (inst["link"] or {}).get("href") or ""
        if not lbl and _href and _href in (out.get("skeleton") or ""):
            out.pop("link", None)
            return out
        cta = {"type": "cta", "nodeType": f"{ns}:cta", "promoted": True,
               "fields": {}, "link": inst["link"]}
        if lbl:
            cta["fields"]["linkLabel"] = str(lbl)[:250]
            cta["linkLabel"] = str(lbl)[:250]
        # EMPTY-SHELL class (2026-07-20, corporate 'About SingPost'): the
        # skeleton may retain the source anchor as an INLINE marker shell
        # (href="{{link:href}}" wrapping {{f:linkLabel}}). Section types
        # declare NO link props, so those markers can never resolve on the
        # parent — the shell rendered an EMPTY button while the lifted child
        # rendered a DUPLICATE outside the layout. Move the shell WITH the
        # lift: it becomes the cta child's OWN skeleton ({ns}:cta declares
        # linkLabel + linkOrig) and {{child:N}} takes its place, so the button
        # renders in its original position through the child's edit frame.
        def _excise_shell(host):
            """Excise the marker anchor from host['skeleton'] into the cta's
            own skeleton, splicing {{child:N}} at its position. True if done."""
            h_sk = host.get("skeleton") or ""
            if "{{link:href}}" not in h_sk:
                return False
            soup_sk = BeautifulSoup(h_sk, "lxml")
            shell = next((a2 for a2 in soup_sk.find_all("a")
                          if (a2.get("href") or "") == "{{link:href}}"), None)
            if shell is None:
                return False
            idx = len(host.get("children") or [])
            cta["skeleton"] = str(shell)
            shell.replace_with(soup_sk.new_string("{{child:%d}}" % idx))
            host["skeleton"] = "".join(
                str(c) for c in (soup_sk.body.children if soup_sk.body else [])).strip()
            host.setdefault("children", []).append(cta)
            return True

        out.pop("link", None)
        if _excise_shell(out):
            pass
        else:
            # pass 2 (2026-07-20): _decompose_repeats may have carved the card
            # holding the marker shell BEFORE this lift ran — the shell then
            # sits DEAD in a cardItem child while the cta appended to the
            # parent renders the button OUTSIDE its card. Nest the cta inside
            # the child that owns the shell, at the shell's position.
            placed = False
            for ch_d in out.get("children") or []:
                if isinstance(ch_d, dict) and _excise_shell(ch_d):
                    placed = True
                    break
            if not placed:
                out.setdefault("children", []).append(cta)
        # the cta owns the label now; a copy stranded on the parent can never
        # render (section/card types declare no linkLabel) — drop it
        if cta["fields"].get("linkLabel") and fields.get("linkLabel") == cta["fields"]["linkLabel"]:
            fields.pop("linkLabel", None)
    # CTA label ownership (2026-07-17, enterprise 'Enquire'): the cta CHILD
    # renders the button; a linkLabel stranded on the PARENT renders nowhere.
    # Transfer it to the first label-less cta child.
    pf = out.get("fields") or {}
    if pf.get("linkLabel"):
        _ctas = [c for c in (out.get("children") or [])
                 if c.get("type") == "cta" or str(c.get("nodeType") or "").endswith(":cta")]
        _tgt = next((c for c in _ctas if not (c.get("fields") or {}).get("linkLabel")), None)
        if _tgt is not None:
            _tgt.setdefault("fields", {})["linkLabel"] = str(pf.pop("linkLabel"))[:250]
            _tgt["linkLabel"] = _tgt["fields"]["linkLabel"]
    return out


def _normalize_slots(instances):
    """FINAL slot-pairing normalization (2026-07-20): every {{f:bodyN}}/
    {{f:labelN}} marker must have its value and every value its marker —
    across ALL decomposition paths (repeats, library atoms, nav swap).
    Pass 1 (top-down): a child's stranded marker PULLS the value from its
    parent (the carve moved structure without content). Untraceable markers
    drop — content already lives in a parent body; a hole helps nobody.
    Pass 2: orphan bodyN/labelN values (no marker anywhere) merge into body so
    the content still renders. reconcile-check gates any leak that survives."""
    flat = list(instances or [])

    def parent_of(it):
        p = it.get("parent")
        if isinstance(p, int) and 0 <= p < len(flat):
            return flat[p]
        return None

    def pass1(items, parent):
        for it in items or []:
            f = it.setdefault("fields", {})
            sk = it.get("skeleton") or ""
            if sk:
                pf = ((parent or parent_of(it)) or {}).get("fields") or {}
                for mk in set(re.findall(r"\{\{f:(body\d+|label\d*)\}\}", sk)):
                    if (f.get(mk) or "").strip():
                        continue
                    if (pf.get(mk) or "").strip():
                        f[mk] = pf.pop(mk)
                    else:
                        sk = sk.replace("{{f:%s}}" % mk, "")
                it["skeleton"] = sk
            pass1(it.get("children"), it)

    def pass2(items):
        for it in items or []:
            f = it.get("fields") or {}
            sk = it.get("skeleton") or ""
            for fk in [k for k in list(f)
                       if re.match(r"(body\d+|label\d+)$", k)]:
                v = f.get(fk)
                if not (isinstance(v, str) and v.strip()):
                    continue
                if sk and "{{f:%s}}" % fk in sk:
                    continue
                f.pop(fk)
                merged = v if fk.startswith("body") else f"<p>{v}</p>"
                f["body"] = "\n".join(
                    x for x in [f.get("body", ""), merged] if x).strip()
                if sk and "{{f:body}}" not in sk:
                    sk += "{{f:body}}"
                    it["skeleton"] = sk
            pass2(it.get("children"))

    def pass3(items):
        # OVER-FRAGMENTATION (gate 2026-07-20, Text(2)..Text(23)): slots
        # beyond the 4th become cardItem CHILDREN — the marker turns into
        # {{child:N}} at the same position, the value becomes the child's
        # editable body. Applies on ALL paths (extract text runs included).
        for it in items or []:
            f = it.get("fields") or {}
            sk = it.get("skeleton") or ""
            slots = sorted((k for k in f if re.match(r"body\d+$", k)),
                           key=lambda k: int(k[4:]))
            if len(slots) <= 3:
                pass3(it.get("children"))
                continue
            ns = (it.get("nodeType") or "x:y").split(":")[0]
            kids = it.setdefault("children", [])
            for k in slots[3:]:
                marker = "{{f:%s}}" % k
                if marker not in sk:
                    continue
                idx = len(kids)
                sk = sk.replace(marker, "{{child:%d}}" % idx, 1)
                kids.append({"type": "cardItem", "nodeType": f"{ns}:cardItem",
                             "promoted": True,
                             "fields": {"body": f.pop(k)},
                             "skeleton": "{{f:body}}"})
            it["skeleton"] = sk
            pass3(it.get("children"))

    pass1(flat, None)
    pass2(flat)
    pass3(flat)


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
        # {{f:*}}/{{media:*}}/{{child:N}} markers are STRUCTURE, not visible
        # text — counting their names as content inflated orig_vis and failed
        # conservation on pages that were actually fully placed.
        html = re.sub(r"\{\{[^{}]*\}\}", " ", html or "")
        if not html or "<" not in html:
            return re.sub(r"\s+", " ", html).strip()
        soup = BeautifulSoup(html, "lxml")
        for el in soup.find_all(["script", "style", "noscript", "template"]):
            el.extract()
        return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()

    n_sem = n_pass = n_drop = 0
    recon_pages = {}
    chrome_capture = {}
    for _pk, page in data.get("pages", {}).items():
        recon_rows = []
        recon_pages[_pk] = recon_rows
        drop_reason = {}
        # ARCHETYPE model: the fidelity `shell` spec (full source body around
        # <main> — nav/cookie-consent/notification chrome + SPA state) is NOT
        # used by the semantic Layout and must not become a 100KB rawHtml blob
        # node editors see in jContent. Drop it; the Layout falls back to the
        # css-manifest for source styling (scripts intentionally excluded).
        _sh = page.get("shell") or {}
        if _sh.get("mainAttrs") and not recon_pages.get("_mainAttrs"):
            os.makedirs(f"projects/{a.project}/workflow-output", exist_ok=True)
            json.dump({"mainAttrs": _sh.get("mainAttrs") or {},
                       "bodyAttrs": _sh.get("bodyAttrs") or {}},
                      open(f"projects/{a.project}/workflow-output/main-attrs.json", "w"))
            recon_pages["_mainAttrs"] = True
        page.pop("shell", None)
        # RECONCILIATION accounting (process-hardening 2026-07-16): source
        # visible text per instance BEFORE transformation — conservation is
        # gated (reconcile-check), never assumed.
        orig_vis, orig_text = {}, {}
        for _i, _inst in enumerate(page.get("instances", [])):
            _parts = [v for v in (_inst.get("fields") or {}).values()
                      if isinstance(v, str)]
            for _k in ("skeleton", "imgOrig"):
                if isinstance(_inst.get(_k), str):
                    _parts.append(_inst[_k])
            _ot = _visible(" ".join(_parts))
            orig_vis[_i] = len(_ot)
            orig_text[_i] = _ot
        # library plans WITH paired atoms decompose via _decompose_library;
        # a plan WITHOUT atoms is a bare slide track needing the gallery rescue
        _plans_with_atoms = {a2.get("parent") for a2 in page.get("instances", [])
                             if a2.get("libraryAtom") and a2.get("parent") is not None}
        transformed = []                       # (keep: bool, instance | None)
        for _oi, inst in enumerate(page.get("instances", [])):
            if inst.get("area"):
                # ARCHETYPE model: captured source chrome (rawHtml routed to an
                # absolute area — the source's own header/nav/footer markup with
                # its SPA islands) is REPLACED by contributed Jahia chrome
                # (build_nav_tree places mainNavigation/siteHeader/footer), so
                # passthrough-typed area captures are dropped. A semantic-typed
                # area singleton (none today) would still pass through.
                node = itm.get((inst.get("type") or "").lower())
                if node is None or node == passthrough:
                    # persist the capture (first-seen per area): populate_chrome
                    # turns it into EDITABLE chrome content (logo, top links,
                    # footer columns) — dropped from pages, never lost
                    _area = inst.get("area") or "chrome"
                    _html = (inst.get("fields") or {}).get("html", "") or inst.get("skeleton", "")
                    if _html and _area not in chrome_capture:
                        chrome_capture[_area] = _clean_html(_html)
                    transformed.append((False, None))
                    drop_reason[len(transformed) - 1] = "chrome"
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
                    # GALLERY RESCUE (2026-07-17): a plan with NO paired atoms
                    # is a bare slide track — the sweep below would flatten its
                    # slides into body as stacked full-width images (careers
                    # culture section, 5175px vs the source's one-row track).
                    # Decompose the slides into cardItem children FIRST and
                    # demote the plan to a plain promoted instance: the
                    # loader's standard item-N path creates the slides, each
                    # editable, spliced back into the track via {{child:N}}.
                    if _oi not in _plans_with_atoms and inst.get("skeleton")                             and "{{child:" not in inst["skeleton"]:
                        _rns = (inst.get("nodeType") or "x:y").split(":")[0]
                        _rsk, _rkids = _decompose_repeats(
                            inst["skeleton"], _rns, inst.get("media"),
                            parent_fields=inst.setdefault("fields", {}))
                        if _rkids:
                            inst["skeleton"] = _rsk
                            inst["children"] = _rkids
                            inst.pop("libraryPlan", None)
                            inst["promoted"] = True
                    # the container's OWN text (heading + inline markup around
                    # the {{child}} markers — the hero lived there) is invisible
                    # to the semantic views inside the skeleton prop: surface it
                    # as title/body fields so the archetype view renders it.
                    f = inst.setdefault("fields", {})
                    # CONTRACT v2: containers own body too — runs/labels merge INTO it
                    sk_l = inst.get("skeleton") or ""
                    parts = [f.get("body")] if isinstance(f.get("body"), str) else []
                    for k in [k for k in sorted(f, key=lambda k: (len(k), k))
                              if re.match(r"(body\d+|label\d*)$", k)]:
                        v = f.pop(k)
                        if isinstance(v, str) and v.strip():
                            parts.append(v if k.startswith("body") else f"<p>{v}</p>")
                        sk_l = sk_l.replace("{{f:%s}}" % k, "", 1)
                    merged_l = "\n".join(p for p in parts if p and p.strip()).strip()
                    if merged_l:
                        f["body"] = merged_l
                        if "{{f:body}}" not in sk_l and sk_l:
                            sk_l += "{{f:body}}"
                    if sk_l:
                        inst["skeleton"] = sk_l
                    if not f.get("title") and inst.get("skeleton"):
                        t, _b = _split_skeleton(inst["skeleton"])
                        if t:
                            f["title"] = t
                    # sweep DEFERRED to _decompose_library (2026-07-17): it
                    # must run AFTER the slide fragments swap to {{child:N}} —
                    # swept first, the slides land in body as stacked images
                    # and the imageFile anchors vanish from the skeleton.
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
                drop_reason[len(transformed) - 1] = "empty"
                n_drop += 1
        # library containers: verbatim item fragments -> {{child:N}} + per-item
        # skeleton/fields (Page Builder selection + Content Editor truth)
        _decompose_library(transformed, (passthrough or "x:y").split(":")[0])
        # reconciliation rows: placed (fields+children) vs leftover (residual
        # skeleton text) vs original — per instance, into reconciliation.json
        def _placed_raw(ins):
            f = ins.get("fields") or {}
            t = " ".join(str(v) for v in (f.get("title"), f.get("body"),
                                          f.get("linkLabel")) if v)
            for ch in (ins.get("children") or []):
                cf = ch.get("fields") or {}
                t += " " + " ".join(str(v) for v in (cf.get("title"), cf.get("body"),
                                                     cf.get("linkLabel"), ch.get("linkLabel")) if v)
            return _visible(t)

        def _placed_text(ins):
            return len(_placed_raw(ins))

        def _leftover_text(ins):
            sk_ = re.sub(r"\{\{[^}]+\}\}", " ", ins.get("skeleton") or "")
            return len(_visible(sk_))

        for _i, (_keep, _ins) in enumerate(transformed):
            row = {"page": None, "idx": _i, "before": orig_vis.get(_i, 0),
                   "_ot": orig_text.get(_i, "")}
            if not _keep or _ins is None:
                row.update({"kind": f"dropped-{drop_reason.get(_i, 'unknown')}",
                            "placed": 0, "leftover": 0})
            else:
                # atoms were absorbed as children of their container: their own
                # row shows the container reference, text counted on the parent
                _pl, _lo = _placed_text(_ins), _leftover_text(_ins)
                row.update({"kind": ("library" if (_ins.get("libraryPlan") or _ins.get("libraryAtom"))
                                     else ("passthrough" if _ins.get("passthrough") else "typed")),
                            "type": _ins.get("type"), "nodeType": _ins.get("nodeType"),
                            "atom": bool(_ins.get("libraryAtom")),
                            "parent": _ins.get("parent"),
                            "placed": _pl, "leftover": _lo})
                # EVIDENCE, not counts: when a row under-places, name the words
                if orig_vis.get(_i, 0) > 80 and (_pl + _lo) < orig_vis[_i] * 0.8:
                    f2 = _ins.get("fields") or {}
                    have = " ".join(str(v) for v in f2.values() if isinstance(v, str))
                    for ch2 in (_ins.get("children") or []):
                        have += " " + " ".join(str(v) for v in (ch2.get("fields") or {}).values()
                                               if isinstance(v, str))
                    have_w = set(re.findall(r"\w{4,}", _visible(have).lower()))
                    miss = [w for w in re.findall(r"\w{4,}", orig_text.get(_i, "").lower())
                            if w not in have_w]
                    if miss:
                        row["missingSample"] = " ".join(dict.fromkeys(miss))[:300]
            recon_rows.append(row)
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
        _normalize_slots(kept)

    # write the reconciliation artifact (orchestrator-reviewable; gated by
    # orchestration/probes/reconcile-check.py BEFORE any load)
    recon = {"project": a.project, "pages": {}}
    recon_pages.pop("_mainAttrs", None)
    for _pk, rows in recon_pages.items():
        by_idx = {r["idx"]: r for r in rows}
        for r in rows:
            if r.get("atom") and r.get("parent") is not None:
                par = by_idx.get(r["parent"])
                if par:
                    par["before"] = max(par["before"] - r["before"], 0)
        before = sum(r["before"] for r in rows)
        placed = sum(r.get("placed", 0) for r in rows)
        leftover = sum(r.get("leftover", 0) for r in rows)
        # conservation is WORD-level: decomposition legitimately moves text
        # ACROSS rows (container -> items), so per-row char counts can neither
        # detect loss nor avoid false alarms. The truth question is: does every
        # source word exist somewhere AUTHORABLE in the FINAL payload (sweeps
        # and merges run after row capture)? The gap is NAMED, never counted.
        _w = lambda t: set(re.findall(r"[^\W\d_]{3,}", (t or "").lower()))
        need = set()
        for r in rows:
            if not str(r.get("kind", "")).startswith("dropped-") or r.get("kind") == "dropped-unknown":
                need |= _w(r.pop("_ot", ""))
            else:
                r.pop("_ot", None)

        def _auth_words(ins):
            out = set()
            for v in (ins.get("fields") or {}).values():
                if isinstance(v, str):
                    out |= _w(_visible(v))
            out |= _w(_visible(ins.get("skeleton") or ""))
            for ch in (ins.get("children") or []):
                out |= _auth_words(ch)
            return out
        have = set()
        for ins in (data.get("pages", {}).get(_pk) or {}).get("instances", []):
            have |= _auth_words(ins)
        missing = sorted(need - have)
        # by-design drops (replaced chrome, zero-visible fragments) are NOT
        # content loss — conservation measures the CONTENT instances only
        excluded = sum(r["before"] for r in rows
                       if str(r.get("kind", "")).startswith("dropped-")
                       and r["kind"] in ("dropped-chrome", "dropped-empty"))
        lost = sum(r["before"] for r in rows if r.get("kind") == "dropped-unknown")
        eff = max(before - excluded, 0)
        recon["pages"][_pk] = {
            "before": before, "beforeEffective": eff, "placed": placed,
            "leftover": leftover, "excludedByDesign": excluded, "lost": lost,
            "coverage": round(len(need & have) / len(need), 3) if need else 1.0,
            "words": len(need), "missingWords": missing[:120],
            "rows": rows}
    if chrome_capture:
        cp = f"projects/{a.project}/workflow-output/chrome-capture.json"
        json.dump(chrome_capture, open(cp, "w"), indent=1, ensure_ascii=False)
        print(f"[semanticize_content] chrome capture -> {cp} ({', '.join(chrome_capture)})")
    rp = f"projects/{a.project}/workflow-output/reconciliation.json"
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    json.dump(recon, open(rp, "w"), indent=1, ensure_ascii=False)
    print(f"[semanticize_content] reconciliation -> {rp}")

    data["adapter"] = "semantic"
    data["model"] = "archetype"
    out = a.out or load_p
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print(f"[semanticize_content] {out}: {n_sem} semantic instance(s), "
          f"{n_pass} passthrough, over {len(data.get('pages', {}))} page(s)")


if __name__ == "__main__":
    main()
