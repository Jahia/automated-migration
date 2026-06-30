#!/usr/bin/env python3
"""Deterministic Sitecore SXA component extractor.

Sitecore SXA declares component boundaries in the DOM:
    <div class="component <TYPE> …">      one component instance; class after
       <div class="component-content">    'component' (minus layout utils) = its type
          …class="field-<NAME>"…          each field-* = one editable property

So the rendered DOM is a COMPLETE, machine-readable component+field map. This walks
it and emits every component type, its field-* properties, nested child component
types, and instance counts — a reproducible inventory, unlike LLM "eyeball the page"
discovery which silently drops small/peripheral components (top-bar, contact-block…).

Usage:
    sxa-extract.py <html-file-or-dir> [more…]      → JSON inventory on stdout
"""
import sys, re, json, glob, os
from html.parser import HTMLParser

# bootstrap / SXA layout + state classes that are NOT the semantic component type
LAYOUT = re.compile(
    r"^(component-content|container|container-fluid|row|col|col-\w+|mb-\d+|mt-\d+|"
    r"mx-\w+|my-\w+|m-\d+|px-\d+|py-\d+|p-\d+|pt-\d+|pb-\d+|ps-\d+|pe-\d+|ms-\w+|me-\w+|"
    r"g-\d+|gap-\d+|align-\w+|align-items-\w+|justify-\w+|justify-content-\w+|"
    r"d-\w+|d-md-\w+|d-lg-\w+|d-md-down-none|text-\w+|fs-\w+|fw-\w+|w-\d+|h-\d+|mw-\d+|"
    r"height0|parent-row|clearfix|initialized|active|show|first|last|odd|even|"
    r"rel-level\d|level\d|item\d+|submenu|background-img)$"
)

def semantic(after):
    sem = [c for c in after if not LAYOUT.match(c)]
    return sem or after or ["unknown"]

class SXA(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.divdepth = 0
        self.compstack = []     # (component_index, open_divdepth)
        self.components = []     # per-instance dicts

    def _collect_fields(self, attrs):
        cls = (dict(attrs).get("class") or "").split()
        for t in cls:
            if t.startswith("field-") and self.compstack:
                self.components[self.compstack[-1][0]]["fields"].add(t[len("field-"):])

    def handle_starttag(self, tag, attrs):
        self._collect_fields(attrs)
        if tag != "div":
            return
        self.divdepth += 1
        toks = (dict(attrs).get("class") or "").split()
        if "component" in toks:
            after = [t for t in toks if t not in ("component", "component-content")]
            sem = semantic(after)
            idx = len(self.components)
            parent = self.compstack[-1][0] if self.compstack else None
            self.components.append({
                "type": sem[0], "aliases": sem, "fields": set(), "children": set(),
                "parent": (self.components[parent]["type"] if parent is not None else None),
            })
            if parent is not None:
                self.components[parent]["children"].add(sem[0])
            self.compstack.append((idx, self.divdepth))

    def handle_startendtag(self, tag, attrs):
        self._collect_fields(attrs)

    def handle_endtag(self, tag):
        if tag != "div":
            return
        if self.compstack and self.compstack[-1][1] == self.divdepth:
            self.compstack.pop()
        self.divdepth = max(0, self.divdepth - 1)

def files(args):
    out = []
    for a in args:
        if os.path.isdir(a):
            out += glob.glob(os.path.join(a, "**", "*.html"), recursive=True)
        else:
            out.append(a)
    return out

def main():
    paths = files(sys.argv[1:] or ["."])
    agg = {}   # type -> {fields:set, children:set, instances:int, pages:set}
    for f in paths:
        try:
            html = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        if "component-content" not in html:
            continue  # not an SXA-rendered page
        p = SXA(); p.feed(html)
        page = os.path.basename(f)
        for c in p.components:
            a = agg.setdefault(c["type"], {"fields": set(), "children": set(), "instances": 0, "pages": set(), "aliases": set()})
            a["fields"] |= c["fields"]; a["children"] |= c["children"]
            a["instances"] += 1; a["pages"].add(page); a["aliases"] |= set(c["aliases"])
    inventory = []
    for t, a in sorted(agg.items(), key=lambda kv: -kv[1]["instances"]):
        inventory.append({
            "type": t,
            "aliases": sorted(a["aliases"]),
            "fields": sorted(a["fields"]),
            "childTypes": sorted(a["children"]),
            "isContainer": bool(a["children"]),
            "instances": a["instances"],
            "pages": sorted(a["pages"])[:8],
        })
    print(json.dumps({
        "sourceIsSxa": len(inventory) > 0,
        "componentTypeCount": len(inventory),
        "components": inventory,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
