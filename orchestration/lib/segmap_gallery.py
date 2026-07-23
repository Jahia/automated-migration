#!/usr/bin/env python3
"""segmap_gallery — zone-overlay/index.html for the model-review UI card.

The orchestrator UI's "🗺 Carte de zonage" card links to
GET /runs/{id}/artifacts/zone-overlay/index.html. The old zone-bridge pipeline
produced that gallery via zone_to_contentload --overlay + zone_overlay_probe;
the v3 archetype pipeline's boundary evidence is the SEGMAP overlays the vision
segmentation already writes per page (segment/<slug>.segmap.html + .page.png).
This emits the gallery over those, with the consensus verdict per page, so the
review card's link always resolves (2026-07-23: it 404'd on the singpost run).

Usage: segmap_gallery.py <project>
"""
import glob
import html as _h
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main(project):
    wo = f"{REPO}/projects/{project}/workflow-output"
    segdir = f"{wo}/segment"
    outdir = f"{wo}/zone-overlay"
    rows = []
    for f in sorted(glob.glob(f"{segdir}/*.segmentation.json")):
        slug = os.path.basename(f)[: -len(".segmentation.json")]
        try:
            s = json.load(open(f))
        except Exception:
            continue
        comps = [c.get("name") or "?" for c in (s.get("components") or [])]
        green = bool(s.get("gatePass") or s.get("adjudicated"))
        by = "adjudication" if s.get("adjudicated") else (
            "stability" if s.get("gatePass") else "RED")
        segmap = f"{segdir}/{slug}.segmap.html"
        png = f"{segdir}/{slug}.page.png"
        rows.append((slug, comps, s.get("agreement"), by, green,
                     os.path.exists(segmap), os.path.exists(png)))
    os.makedirs(outdir, exist_ok=True)
    tr = []
    for slug, comps, agr, by, green, has_map, has_png in rows:
        links = []
        if has_map:
            links.append(f'<a href="../segment/{_h.escape(slug)}.segmap.html" '
                         f'target="_blank">carte</a>')
        if has_png:
            links.append(f'<a href="../segment/{_h.escape(slug)}.page.png" '
                         f'target="_blank">page</a>')
        color = "#0a0" if green else "#c00"
        tr.append(
            f"<tr><td><code>{_h.escape(slug)}</code></td>"
            f"<td>{_h.escape(' · '.join(comps))}</td>"
            f"<td style='color:{color}'>{by}"
            f"{'' if agr is None else f' ({agr})'}</td>"
            f"<td>{' | '.join(links) or '—'}</td></tr>")
    n_green = sum(1 for r in rows if r[4])
    html = f"""<!doctype html><meta charset="utf-8">
<title>Carte de zonage — {_h.escape(project)}</title>
<style>body{{font:14px/1.5 -apple-system,sans-serif;margin:2rem;color:#001932}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #dae0e7;
padding:.4rem .6rem;text-align:left;vertical-align:top}}code{{font-size:12px}}
th{{font-size:11px;text-transform:uppercase;color:#7d8a9a}}</style>
<h1>Carte de zonage — frontières des composants ({_h.escape(project)})</h1>
<p>{len(rows)} page(s), {n_green} verte(s). La « carte » ouvre l'overlay de
segmentation (frontières numérotées sur le DOM rendu) ; « page » la capture.</p>
<table><tr><th>page</th><th>composants (racines)</th><th>verdict</th>
<th>artefacts</th></tr>{''.join(tr)}</table>"""
    open(f"{outdir}/index.html", "w").write(html)
    print(f"segmap_gallery: {len(rows)} page(s) -> {outdir}/index.html")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: segmap_gallery.py <project>")
    main(sys.argv[1].split("/")[-1])
