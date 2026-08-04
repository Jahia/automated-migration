#!/usr/bin/env python3
"""segmap_gallery — zone-overlay/index.html for the model-review UI card.

The orchestrator UI's "🗺 Carte de zonage" card links to
GET /runs/{id}/artifacts/zone-overlay/index.html. The old zone-bridge pipeline
produced that gallery via zone_to_contentload --overlay + zone_overlay_probe;
the v3 archetype pipeline's boundary evidence is the SEGMAP overlays the vision
segmentation already writes per page (segment/<slug>.segmap.html + .page.png).
This emits the gallery over those, with the consensus verdict per page, so the
review card's link always resolves (2026-07-23: it 404'd on the singpost run).

DECLARED SOURCES have no segmaps (they skip vision segmentation by design), which
left the card rendering an empty table — bytes on disk, nothing in it. On that arm
the gallery is built from the declaration instead: one row per manual-inspector
page, its declared component roots, and the band count the census measured.

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

    # THE DECLARED ARM HAS NO SEGMAPS, AND ITS EVIDENCE IS BETTER (2026-08-04).
    # This gallery reads what the VISION segmentation writes per page. A source whose
    # CMS declares its own component boundaries skips segmentation entirely by design,
    # so segdir is empty, every row is empty, and the review card's "Carte de zonage"
    # renders a 701-byte page with a table of nothing — which `test -s` happily passes.
    # Third consumer found today that only knew the vision arm (after make_overrides
    # and site_inventory), so the pattern is worth naming: when the adapter path was
    # added, the artifacts it does NOT produce were never traced to their readers.
    #
    # On this arm the boundary evidence is the DECLARATION itself, and the per-page
    # artifact is the manual inspector page (<slug>.manual.html) that the cockpit's
    # Zoning tab already serves — a live, clickable overlay of the real DOM, strictly
    # more useful than a screenshot. The verdict column becomes the band count the
    # census measured for that page, which is the number the model was built from.
    if not rows:
        mirror = f"{wo}/local-mirror"
        try:
            census = json.load(open(f"{wo}/model-census.json"))
        except (OSError, ValueError):
            census = {}
        per_page = census.get("bandsPerPage") or {}
        declared_names = {}
        try:
            dec = json.load(open(f"{REPO}/projects/{project}/.reference/"
                                 "declared-components.json"))
            adapter = dec.get("adapter") or "declared"
        except (OSError, ValueError):
            adapter = "declared"
        import re as _re
        _DECL = _re.compile(r'class="[^"]*\bcomponent\s+([a-z][a-z0-9-]{2,30})')
        for f in sorted(glob.glob(f"{mirror}/*.manual.html")):
            slug = os.path.basename(f)[: -len(".manual.html")]
            n = per_page.get(slug)
            if slug not in declared_names:
                seen, names = set(), []
                try:
                    _html = open(f"{mirror}/{slug}.html", encoding="utf-8",
                                 errors="replace").read()
                    # CONTENT bands only: scanning the whole page led every row with
                    # top-bar / header-navigation / navigation, i.e. the chrome that is
                    # identical on all 263 pages and says nothing about the page
                    _m = _re.search(r"<main[^>]*>(.*?)</main>", _html, _re.S | _re.I)
                    for nm in _DECL.findall(_m.group(1) if _m else _html):
                        if nm not in seen and nm != "content-wrapper":
                            seen.add(nm)
                            names.append(nm)
                except OSError:
                    names = []
                declared_names[slug] = names[:8]
            comps = declared_names.get(slug) or []
            rows.append((slug, comps, n, f"{adapter} ({n} band(s))" if n
                         else adapter, n is not None and n > 0, False, False,
                         True))
        if rows:
            print(f"  ~ no vision segmaps — gallery built from the {adapter} "
                  f"declaration over {len(rows)} inspector page(s)", file=sys.stderr)

    # normalise row arity (the declared arm adds a `has_manual` field)
    rows = [r if len(r) == 8 else (*r, False) for r in rows]
    os.makedirs(outdir, exist_ok=True)
    tr = []
    for slug, comps, agr, by, green, has_map, has_png, has_manual in rows:
        links = []
        if has_manual:
            links.append(f'<a href="/projects/{_h.escape(project)}/zoning/mirror/'
                         f'{_h.escape(slug)}.manual.html" target="_blank">inspecteur</a>')
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
            f"<td style='color:{color}'>{_h.escape(str(by))}</td>"
            f"<td>{' | '.join(links) or '—'}</td></tr>")
    n_green = sum(1 for r in rows if r[4])
    html = f"""<!doctype html><meta charset="utf-8">
<title>Carte de zonage — {_h.escape(project)}</title>
<style>body{{font:14px/1.5 -apple-system,sans-serif;margin:2rem;color:#001932}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #dae0e7;
padding:.4rem .6rem;text-align:left;vertical-align:top}}code{{font-size:12px}}
th{{font-size:11px;text-transform:uppercase;color:#7d8a9a}}</style>
<h1>Carte de zonage — frontières des composants ({_h.escape(project)})</h1>
<p>{len(rows)} page(s), {n_green} avec des bandes détectées. « inspecteur » ouvre
l'overlay cliquable sur le DOM réel (source déclarante : la déclaration EST la
frontière) ; « carte » / « page » l'overlay de segmentation et sa capture quand la
segmentation visuelle a tourné.</p>
<table><tr><th>page</th><th>composants (racines)</th><th>verdict</th>
<th>artefacts</th></tr>{''.join(tr)}</table>"""
    open(f"{outdir}/index.html", "w").write(html)
    print(f"segmap_gallery: {len(rows)} page(s) -> {outdir}/index.html")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: segmap_gallery.py <project>")
    main(sys.argv[1].split("/")[-1])
