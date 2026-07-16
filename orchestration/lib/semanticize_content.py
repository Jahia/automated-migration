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


def _sweep_text_to_body(sk, fields, min_chars=60):
    """Selective authorability sweep: maximal text-bearing elements WITHOUT any
    marker move into the body field; marker-bearing structure stays."""
    resid = re.sub(r"\{\{[^}]+\}\}", " ", sk or "")
    resid = re.sub(r"<[^>]+>", " ", resid)
    if not sk or len(re.sub(r"\s+", " ", resid).strip()) < min_chars:
        return sk
    soup = BeautifulSoup(sk, "lxml")
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
    for el in taken:
        el.extract()
    # LOOSE TEXT NODES (the named-debt hoarders): text sitting directly under
    # a marker-bearing wrapper is invisible to the element mover — wrap+move it
    from bs4 import NavigableString
    for tx in list(soup.body.strings if soup.body else []):
        t_s = str(tx)
        if "{{" in t_s or len(t_s.strip()) < 20:
            continue
        moved.append(f"<p>{t_s.strip()}</p>")
        tx.extract()
    if moved:
        fields["body"] = "\n".join(
            x for x in [fields.get("body", ""), *moved] if x).strip()
        sk = "".join(str(c) for c in soup.body.children).strip()
        if "{{f:body}}" not in sk:
            sk += "{{f:body}}"
    return sk


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
        # gate). The root element + classes stay for the source CSS.
        root = next((c for c in (soup.body.children if soup.body else [])
                     if getattr(c, "name", None)), None)
        if root is not None and root.get_text(strip=True):
            body = "".join(str(c) for c in root.children).strip()
            root.clear()
            root.append("{{f:body}}")
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
            if frag in sk:
                sk = sk.replace(frag, "{{child:%d}}" % n, 1)
                swapped += 1
        parent["skeleton"] = sk
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
    # CONTRACT v2 (2026-07-16): authorable content lives in PROPERTIES, never
    # in the hidden skeleton. Every type owns ONE body richtext — text runs 2+,
    # label runs and extra media all MERGE INTO the body VALUE; their markers
    # collapse into the single {{f:body}} slot. Skeleton = structure only.
    sk = out.get("skeleton") or ""
    body_parts = [fields.get("body")] if isinstance(fields.get("body"), str) else []
    for k in sorted((k for k in fields if re.match(r"body\d+$", k)),
                    key=lambda k: (len(k), k)):
        v = fields.pop(k)
        if isinstance(v, str) and v.strip():
            body_parts.append(v)
        sk = sk.replace("{{f:%s}}" % k, "", 1)
    for k in sorted((k for k in fields if re.match(r"label\d*$", k)),
                    key=lambda k: (len(k), k)):
        v = fields.pop(k)
        if isinstance(v, str) and v.strip():
            body_parts.append(f"<p>{v}</p>")
        sk = sk.replace("{{f:%s}}" % k, "", 1)
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
            # markers move to body; marker-bearing structure stays in place)
            sk = _sweep_text_to_body(sk, fields, min_chars=60)
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
        orig_vis = {}
        for _i, _inst in enumerate(page.get("instances", [])):
            _parts = [v for v in (_inst.get("fields") or {}).values()
                      if isinstance(v, str)]
            for _k in ("skeleton", "imgOrig"):
                if isinstance(_inst.get(_k), str):
                    _parts.append(_inst[_k])
            orig_vis[_i] = len(_visible(" ".join(_parts)))
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
                    inst["skeleton"] = _sweep_text_to_body(
                        inst.get("skeleton") or "", f)
                    cm = _distill_classmap(inst.get("skeleton") or "")
                    if cm:
                        inst["classMap"] = cm
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
        def _placed_text(ins):
            f = ins.get("fields") or {}
            t = " ".join(str(v) for v in (f.get("title"), f.get("body"),
                                          f.get("linkLabel")) if v)
            for ch in (ins.get("children") or []):
                cf = ch.get("fields") or {}
                t += " " + " ".join(str(v) for v in (cf.get("title"), cf.get("body"),
                                                     cf.get("linkLabel"), ch.get("linkLabel")) if v)
            return len(_visible(t))

        def _leftover_text(ins):
            sk_ = re.sub(r"\{\{[^}]+\}\}", " ", ins.get("skeleton") or "")
            return len(_visible(sk_))

        for _i, (_keep, _ins) in enumerate(transformed):
            row = {"page": None, "idx": _i, "before": orig_vis.get(_i, 0)}
            if not _keep or _ins is None:
                row.update({"kind": f"dropped-{drop_reason.get(_i, 'unknown')}",
                            "placed": 0, "leftover": 0})
            else:
                # atoms were absorbed as children of their container: their own
                # row shows the container reference, text counted on the parent
                row.update({"kind": ("library" if (_ins.get("libraryPlan") or _ins.get("libraryAtom"))
                                     else ("passthrough" if _ins.get("passthrough") else "typed")),
                            "type": _ins.get("type"), "nodeType": _ins.get("nodeType"),
                            "atom": bool(_ins.get("libraryAtom")),
                            "parent": _ins.get("parent"),
                            "placed": _placed_text(_ins), "leftover": _leftover_text(_ins)})
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
            "coverage": round((placed + leftover) / eff, 3) if eff else 1.0,
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
