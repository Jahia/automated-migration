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


def _semanticize_instance(inst, node, surf):
    """Rewrite one skeleton instance to the archetype field surface."""
    s = surf.get(node) or {}
    fields = inst.get("fields") or {}
    out = {"type": inst["type"], "promoted": True, "fields": {}}
    if inst.get("parent") is not None:
        out["parent"] = inst["parent"]
    title, body = _split_title_body(fields)
    if s.get("title") and title:
        out["fields"]["title"] = title
    if s.get("body") and body:
        out["fields"]["body"] = body
    elif s.get("body") and not body and title and not s.get("title"):
        out["fields"]["body"] = title      # no mix:title -> keep the text in body
    # image: the first lifted media unit -> the media mixin's `image` weakref
    media = inst.get("media") or []
    if s.get("media") and media:
        out["media"] = [{**media[0], "name": "image"}]
    # cta: the lifted link -> j:linkType/j:linknode/j:url (loader wires) + label
    if s.get("cta") and inst.get("link"):
        out["link"] = inst["link"]
        lbl = inst.get("linkLabel") or fields.get("label")
        if lbl:
            out["fields"]["ctaLabel"] = lbl[:250]
    # embedded typed children -> childType surface
    child_node = s.get("child")
    if child_node and inst.get("children"):
        csurf = {child_node: s.get("childSurface", {})}
        out["children"] = [_semanticize_instance({**ch, "type": ch.get("type") or child_node},
                                                 child_node, csurf) for ch in inst["children"]]
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
        transformed = []                       # (keep: bool, instance | None)
        for inst in page.get("instances", []):
            if inst.get("area"):
                transformed.append((True, inst))          # chrome singleton — untouched
                continue
            node = itm.get((inst.get("type") or "").lower())
            typed = (inst.get("promoted") or inst.get("skeleton")) and node and node != passthrough
            if typed:
                transformed.append((True, _semanticize_instance(inst, node, surf)))
                n_sem += 1
            elif len(_visible((inst.get("fields") or {}).get("html", ""))) >= MIN_VIS:
                transformed.append((True, {"type": "rawHtml", "passthrough": True,
                                           "fields": {"html": (inst.get("fields") or {}).get("html", "")}}))
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
