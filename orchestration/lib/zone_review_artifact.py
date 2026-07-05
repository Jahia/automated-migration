#!/usr/bin/env python3
"""zone_review_artifact — emit the human-review artifact for the MODEL gate.

Reads the zone bridge's outputs (content-load.json + component-manifest.json)
and writes a self-contained HTML to workflow-output/zone-review.html: per page,
the zones (z1..zK + chrome) and the nodetype tree inside each, plus the type
inventory and the editorial-quality flags. This is the observability the human
reviews at the halted `model` gate to judge zoning relevance — it is produced by
the pipeline (an engine Run: step), never hand-authored.

Usage: zone_review_artifact.py <project>
"""
import collections
import html as _h
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONT = {"section", "cardGrid", "carousel", "logoWall", "tabs", "accordion", "gridRow"}


def cls(t):
    return "raw" if t == "rawHtml" else ("cont" if t in CONT else "atom")


def build(project):
    cl = json.load(open(f"{REPO}/orchestration/content/{project}.content-load.json"))
    mf = json.load(open(f"{REPO}/projects/{project}/workflow-output/component-manifest.json"))
    pages = cl["pages"]

    def node_html(insts, byparent, idx, depth):
        i = insts[idx]
        kids = byparent.get(idx, [])
        badge = f'<span class="cnt">{len(kids)}</span>' if kids else ""
        inner = ""
        if depth < 2 and kids:
            inner = "<ul>" + "".join(node_html(insts, byparent, c, depth + 1)
                                     for c in kids[:6])
            if len(kids) > 6:
                inner += f'<li class="more">+{len(kids) - 6} autres…</li>'
            inner += "</ul>"
        return f'<li><span class="t {cls(i["type"])}">{_h.escape(i["type"])}</span>{badge}{inner}</li>'

    page_blocks = []
    for slug, p in pages.items():
        insts = p["instances"]
        byparent = collections.defaultdict(list)
        for idx, i in enumerate(insts):
            byparent[i.get("parent")].append(idx)
        zones = collections.OrderedDict()
        for idx in byparent.get(None, []):
            i = insts[idx]
            z = ("⌂ " + i["area"]) if i.get("area") else (i.get("zone") or "main")
            zones.setdefault(z, []).append(idx)
        zg = []
        for zname, idxs in zones.items():
            zc = "chrome" if zname.startswith("⌂") else "zone"
            lis = "".join(node_html(insts, byparent, x, 0) for x in idxs)
            zg.append(f'<div class="zg {zc}"><div class="zh">{_h.escape(zname)}</div>'
                      f'<ul class="tree">{lis}</ul></div>')
        page_blocks.append(
            f'<details class="pg"><summary>{_h.escape(slug)} '
            f'<span class="pc">{len(insts)} inst · {len(zones)} zones</span></summary>'
            f'<div class="zones">{"".join(zg)}</div></details>')

    types = collections.Counter(i["type"] for p in pages.values() for i in p["instances"])
    chips = "".join(f'<span class="chip {cls(t)}">{_h.escape(t)}<b>{c}</b></span>'
                    for t, c in types.most_common())
    q = mf.get("namingQuality", "?")
    gshare = mf.get("genericShare", 0)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Zone review — {project}</title>
<style>
:root{{--ground:#F1F3F6;--surface:#fff;--ink:#181C24;--muted:#697386;--line:#E1E5EC;
--zone:#2E6E9E;--cont:#0E7A6B;--atom:#4A55C7;--raw:#B4590B}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--ground);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:30px 22px 70px}}
h1{{font-size:26px;margin:0 0 4px}}.sub{{color:var(--muted);margin:0 0 18px}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:.86em;background:#e9edf2;padding:1px 5px;border-radius:4px}}
.inv{{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 22px}}
.chip{{font-family:ui-monospace,monospace;font-size:12px;background:var(--surface);border:1px solid var(--line);
border-radius:20px;padding:3px 6px 3px 11px;display:inline-flex;align-items:center;gap:6px}}
.chip b{{color:#fff;border-radius:12px;padding:1px 8px;font-size:11px}}
.chip.cont b{{background:var(--cont)}}.chip.atom b{{background:var(--atom)}}.chip.raw b{{background:var(--raw)}}
.pg{{background:var(--surface);border:1px solid var(--line);border-radius:10px;margin-bottom:8px;overflow:hidden}}
.pg summary{{cursor:pointer;padding:11px 16px;font-family:ui-monospace,monospace;font-size:13px;font-weight:600;
display:flex;justify-content:space-between;gap:12px;list-style:none}}
.pg summary::-webkit-details-marker{{display:none}}
.pc{{color:var(--muted);font-weight:400;font-size:12px}}
.zones{{padding:6px 16px 16px;display:flex;flex-direction:column;gap:12px;border-top:1px solid var(--line)}}
.zg{{border-left:3px solid var(--zone);padding-left:12px}}.zg.chrome{{border-left-color:var(--muted);opacity:.85}}
.zh{{font-family:ui-monospace,monospace;font-size:11px;font-weight:700;text-transform:uppercase;
letter-spacing:.05em;color:var(--zone);margin:6px 0 4px}}.zg.chrome .zh{{color:var(--muted)}}
.tree,.tree ul{{list-style:none;margin:0;padding:0}}
.tree ul{{margin-left:16px;border-left:1px dotted #cbd2dc;padding-left:12px}}.tree li{{margin:2px 0}}
.t{{font-family:ui-monospace,monospace;font-size:12px;font-weight:600;color:var(--c,var(--ink));
border:1px solid color-mix(in srgb,var(--c,#888) 30%,transparent);
background:color-mix(in srgb,var(--c,#888) 8%,#fff);padding:1px 7px;border-radius:5px}}
.t.cont{{--c:var(--cont)}}.t.atom{{--c:var(--atom)}}.t.raw{{--c:var(--raw)}}
.cnt{{font-size:10px;color:var(--muted);margin-left:5px}}.cnt::before{{content:"↳ "}}
.more{{color:var(--muted);font-size:12px;font-style:italic}}
.flag{{background:#FFF6E9;border:1px solid #F0D9A8;border-left:4px solid var(--raw);
border-radius:8px;padding:12px 16px;margin:8px 0 20px;font-size:13.5px}}
</style></head><body><div class="wrap">
<h1>Revue du zonage &amp; content types — {project}</h1>
<p class="sub">{len(pages)} pages · {sum(len(p['instances']) for p in pages.values())} instances ·
zones max/page z1…z{mf.get('zones', 0)} · qualité nommage: <b>{q}</b> (part générique section/rawHtml: {gshare:.0%})</p>
<div class="flag">Chaque type coloré : <span class="t cont">container</span> (on contribue dedans) ·
<span class="t atom">atome</span> (unité de contenu) · <span class="t raw">rawHtml</span> (verbatim non éditable).
Déplie une page pour voir ses zones et l'arbre des nodetypes.</div>
<div class="inv">{chips}</div>
{''.join(page_blocks)}
</div></body></html>"""


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: zone_review_artifact.py <project>")
    project = sys.argv[1]
    out_dir = f"{REPO}/projects/{project}/workflow-output"
    os.makedirs(out_dir, exist_ok=True)
    out = f"{out_dir}/zone-review.html"
    open(out, "w", encoding="utf-8").write(build(project))
    print(f"zone-review artifact -> {out}")


if __name__ == "__main__":
    main()
