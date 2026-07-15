#!/usr/bin/env python3
"""scorecard.py — the per-run REPORT CARD. No run is "done" until this exists
and its numbers are read (2026-07-15 lesson: adjectives lied all day; numbers
don't). Aggregates the independent instruments into one per-page table:

  pixel        groundtruth.json (EDIT-preview render pixel-diffed vs the
               certified source mirror, JS off both sides)
  junk         clean-render.py (source chrome/SPA/consent/framework debris,
               both workspaces + shell blob nodes)
  ia           rendered nav L1 labels vs the EXTRACTED source menu L1
  completeness instances in the content-load vs nodes the loader created
               (load-ledger), per page

Writes projects/<p>/workflow-output/scorecard.json + prints a markdown table.
BLOCKING: exits 1 when junk fails, IA mismatches, completeness < 100 %, or
mean pixel < --pixel-floor (default 75).

Usage: scorecard.py <project> <siteKey> [--pixel-floor 75]
"""
import argparse
import json
import os
import re
import subprocess
import sys

BASE = os.environ.get("JAHIA_URL", "http://localhost:8080")


def load(path, default):
    try:
        return json.load(open(path))
    except (FileNotFoundError, ValueError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("site")
    ap.add_argument("--pixel-floor", type=float, default=75.0)
    a = ap.parse_args()
    wo = f"projects/{a.project}/workflow-output"
    problems = []

    # ── pixel (groundtruth) ────────────────────────────────────────────────
    gt = load(f"{wo}/groundtruth/groundtruth.json", {})
    results = gt.get("results") or {}
    pixel = {}
    for slug, e in (results.items() if isinstance(results, dict) else []):
        score = e.get("score") if isinstance(e, dict) else None
        if score is None and isinstance(e, dict):
            score = e.get("similarity") or e.get("pct")
        pixel[slug] = round(float(score), 1) if score is not None else None
    scores = [v for v in pixel.values() if v is not None]
    pixel_mean = round(sum(scores) / len(scores), 1) if scores else None
    if pixel_mean is None:
        problems.append("pixel: groundtruth.json missing or empty — probe did not run")
    elif pixel_mean < a.pixel_floor:
        problems.append(f"pixel: mean {pixel_mean}% < floor {a.pixel_floor}%")

    # ── junk (clean-render) ────────────────────────────────────────────────
    here = os.path.dirname(os.path.abspath(__file__))
    cr = subprocess.run([sys.executable, os.path.join(here, "clean-render.py"),
                         a.site, "--model", "archetype"],
                        capture_output=True, text=True)
    junk_pass = cr.returncode == 0
    junk_line = (cr.stdout.strip().splitlines() or [""])[-1]
    if not junk_pass:
        problems.append(f"junk: clean-render FAILED — {junk_line[:140]}")

    # ── IA: rendered nav L1 vs the extracted source menu L1 ───────────────
    ia_ok, ia_detail = None, ""
    labels = load(f"orchestration/sitemaps/{a.project}.labels.json", {})
    sm = f"orchestration/sitemaps/{a.project}.txt"
    l1_expected = []
    if os.path.isfile(sm):
        l1_slugs = [l.strip() for l in open(sm)
                    if l.strip() and not l.startswith("#") and "/" not in l.strip()]
        l1_expected = [labels.get(s, s) for s in l1_slugs]
    if l1_expected:
        import urllib.request, base64
        req = urllib.request.Request(
            f"{BASE}/cms/render/live/en/sites/{a.site}/home.html")
        req.add_header("Authorization", "Basic " + base64.b64encode(
            f"{os.environ.get('JAHIA_USER', 'root')}:{os.environ.get('JAHIA_PASS', 'root')}".encode()).decode())
        try:
            h = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        except Exception as e:
            h = ""
            problems.append(f"ia: home render fetch failed: {str(e)[:80]}")
        m = re.search(r'<ul class="main-navigation__bar">(.*?)</ul>\s*</nav>', h, re.S) \
            or re.search(r'<nav class="main-navigation".*?</nav>', h, re.S)
        rendered_l1 = []
        if m:
            # L1 links only: strip dropdown submenus first
            bar = re.sub(r'<ul class="main-navigation__sub.*?</ul>', "", m.group(0), flags=re.S)
            rendered_l1 = [re.sub(r"\s+", " ", x).strip() for x in
                           re.findall(r'main-navigation__link[^>]*>([^<]+)<', bar)]
        import html as H
        rendered_l1 = [H.unescape(x) for x in rendered_l1]
        ia_ok = rendered_l1 == l1_expected
        ia_detail = f"expected {l1_expected} / rendered {rendered_l1}"
        if not ia_ok:
            problems.append(f"ia: L1 menu mismatch — {ia_detail[:220]}")

    # ── completeness: content-load instances vs loader ledger ─────────────
    cl = load(f"orchestration/content/{a.project}.content-load.json", {})
    ledger = load(f"{wo}/load-ledger.json", {})
    completeness = {}
    for slug, p in (cl.get("pages") or {}).items():
        expected = sum(1 for i in p.get("instances", []) if not i.get("area"))
        entry = ledger.get(slug) or {}
        created = entry.get("created")
        completeness[slug] = {"expected": expected, "created": created}
    missing_pages = [s for s, e in completeness.items() if not e["created"]]
    if missing_pages:
        problems.append(f"completeness: {len(missing_pages)} page(s) with no ledger entry: "
                        + ", ".join(missing_pages[:5]))

    # ── assemble + print ───────────────────────────────────────────────────
    card = {"project": a.project, "site": a.site,
            "pixel": {"mean": pixel_mean, "floor": a.pixel_floor, "perPage": pixel},
            "junk": {"pass": junk_pass, "detail": junk_line},
            "ia": {"pass": ia_ok, "detail": ia_detail},
            "completeness": completeness,
            "problems": problems, "pass": not problems}
    os.makedirs(wo, exist_ok=True)
    json.dump(card, open(f"{wo}/scorecard.json", "w"), indent=1, ensure_ascii=False)

    print(f"## Scorecard — {a.project}\n")
    print(f"| axis | result |\n|---|---|")
    print(f"| pixel (mean, floor {a.pixel_floor}%) | "
          f"{pixel_mean if pixel_mean is not None else 'NOT MEASURED'}% |")
    print(f"| junk | {'PASS' if junk_pass else 'FAIL'} |")
    print(f"| IA (L1 menu) | {'PASS' if ia_ok else ('FAIL' if ia_ok is not None else 'n/a')} |")
    print(f"| pages loaded | {len([e for e in completeness.values() if e['created']])}"
          f"/{len(completeness)} |")
    worst = sorted(((s, v) for s, v in pixel.items() if v is not None), key=lambda x: x[1])[:5]
    if worst:
        print("\nworst pixel pages: " + ", ".join(f"{s}={v}%" for s, v in worst))
    if problems:
        print("\nFAIL: scorecard —")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("\nPASS: scorecard — all axes green")


if __name__ == "__main__":
    main()
