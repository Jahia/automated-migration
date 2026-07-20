#!/usr/bin/env python3
"""diff_forensics.py — locate WHERE a page diverges, not just how much.

Operator doctrine (2026-07-19): 'everytime harden core harness' — the diff
forensics protocol (red-band density -> crop hottest band ref|live -> DOM ->
JCR -> pipeline line) was living in throwaway /tmp scripts; this makes step 1
and 2 a permanent harness tool.

For each page: read groundtruth/<slug>.diff.png, compute red-pixel density per
horizontal band, print the table, and write side-by-side crops of the hottest
bands (ref|live) to workflow-output/forensics/<slug>.band<Y>.png.

Usage: diff_forensics.py <project> [--pages a,b] [--band 300] [--top 3]
"""
import json
import os
import sys

from PIL import Image

BAND = 300


def band_table(diff_path, band):
    im = Image.open(diff_path).convert("RGB")
    w, h = im.size
    px = im.load()
    rows = []
    for y0 in range(0, h, band):
        y1 = min(y0 + band, h)
        red = tot = 0
        for y in range(y0, y1, 3):          # 3px sampling: 9x faster, same signal
            for x in range(0, w, 3):
                r, g, b = px[x, y]
                tot += 1
                if r > 180 and g < 120 and b < 120:
                    red += 1
        rows.append((y0, y1, (100.0 * red / tot) if tot else 0.0))
    return rows, (w, h)


def crop_pair(ref_p, live_p, y0, y1, out_p):
    ref = Image.open(ref_p).convert("RGB")
    live = Image.open(live_p).convert("RGB")
    w = max(ref.size[0], live.size[0])
    rc = ref.crop((0, min(y0, ref.size[1]), ref.size[0], min(y1, ref.size[1])))
    lc = live.crop((0, min(y0, live.size[1]), live.size[0], min(y1, live.size[1])))
    hh = max(rc.size[1], lc.size[1], 1)
    canvas = Image.new("RGB", (w * 2 + 8, hh), (255, 255, 0))
    canvas.paste(rc, (0, 0))
    canvas.paste(lc, (w + 8, 0))
    canvas.save(out_p)


def main():
    project = sys.argv[1]
    band = int(sys.argv[sys.argv.index("--band") + 1]) if "--band" in sys.argv else BAND
    top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 3
    only = None
    if "--pages" in sys.argv:
        only = sys.argv[sys.argv.index("--pages") + 1].split(",")
    gt = f"projects/{project}/workflow-output/groundtruth"
    outdir = f"projects/{project}/workflow-output/forensics"
    os.makedirs(outdir, exist_ok=True)
    report = {}
    slugs = sorted(f[:-9] for f in os.listdir(gt) if f.endswith(".diff.png"))
    for slug in slugs:
        if only and slug not in only:
            continue
        rows, (w, h) = band_table(f"{gt}/{slug}.diff.png", band)
        hot = sorted(rows, key=lambda r: -r[2])[:top]
        print(f"== {slug} ({w}x{h})")
        for y0, y1, pct in rows:
            mark = " <== HOT" if (y0, y1, pct) in hot and pct > 5 else ""
            print(f"   {y0:>6}-{y1:<6} {pct:5.1f}%{mark}")
        report[slug] = [{"y0": y0, "y1": y1, "redPct": round(p, 1)} for y0, y1, p in rows]
        for y0, y1, pct in hot:
            if pct <= 5:
                continue
            crop_pair(f"{gt}/{slug}.ref.png", f"{gt}/{slug}.live.png",
                      y0, y1, f"{outdir}/{slug}.band{y0}.png")
    json.dump(report, open(f"{outdir}/bands.json", "w"), indent=1)
    print(f"\ncrops + bands.json -> {outdir}/")


if __name__ == "__main__":
    main()
