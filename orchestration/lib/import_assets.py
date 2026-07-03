#!/usr/bin/env python3
"""import_assets.py — mirror assets -> module static/ (QUALITY-PLAN P1, step_assets).

The certified local mirror is the fidelity reference: its hashed assets ARE the
site's CSS/fonts/images, and its pages reference them as `assets/<hash>.<ext>`.
This copies them verbatim into the module (`static/assets/`, `static/
runtime-assets/`) and derives the ORDERED stylesheet manifest the Layout must
load (union across pages, first-seen order — cascade order matters) plus the
union of inline <head> <style> blocks (`static/assets/inline-head.css`).

Deterministic, re-runnable. Writes:
  <module>/static/assets/**            (+ runtime-assets/** if any)
  <module>/static/assets/inline-head.css
  <module>/src/templates/css-manifest.json   (imported by Layout.tsx)
Also ensures package.json jahia.static-resources includes /static/assets.

Usage: import_assets.py <project> [--module-dir DIR]
"""
import argparse
import json
import os
import re
import shutil
import sys

LINK_RE = re.compile(
    r'<link\b[^>]*rel=["\']?stylesheet["\']?[^>]*>', re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
STYLE_RE = re.compile(r'<style\b[^>]*>(.*?)</style>', re.I | re.S)
HEAD_RE = re.compile(r'<head\b[^>]*>(.*?)</head>', re.I | re.S)
SCRIPT_RE = re.compile(r'<script\b([^>]*)>', re.I)
SRC_RE = re.compile(r'src=["\']([^"\']+)["\']', re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--module-dir")
    a = ap.parse_args()
    proj = f"projects/{a.project}"
    module = a.module_dir or proj
    mirror = f"{proj}/workflow-output/local-mirror"
    if not os.path.isdir(f"{mirror}/assets"):
        sys.exit(f"FAIL: {mirror}/assets missing (run localize + mirror gate first)")

    # 1. copy hashed assets verbatim (names ARE the contract with page markup)
    n_assets = 0
    for sub in ("assets", "runtime-assets"):
        src = f"{mirror}/{sub}"
        if not os.path.isdir(src):
            continue
        dst = f"{module}/static/{sub}"
        os.makedirs(dst, exist_ok=True)
        for dp, _, fs in os.walk(src):
            for fn in fs:
                s = os.path.join(dp, fn)
                d = os.path.join(dst, os.path.relpath(s, src))
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copyfile(s, d)
                n_assets += 1

    # 2. ordered stylesheet + HEAD script union + inline head styles across
    #    mirror pages (body scripts travel inside the per-page shell spec)
    css_order, seen = [], set()
    js_order, js_seen = [], set()
    inline_blocks, inline_seen = [], set()
    pages = sorted(f for f in os.listdir(mirror) if f.endswith(".html")
                   and not f.endswith(".recon.html"))
    for fn in pages:
        html = open(os.path.join(mirror, fn), errors="replace").read()
        head_m = HEAD_RE.search(html)
        head = head_m.group(1) if head_m else html
        for link in LINK_RE.findall(head):
            href_m = HREF_RE.search(link)
            if not href_m:
                continue
            href = href_m.group(1)
            if href.startswith(("http:", "https:", "//")):
                continue  # mirror gate guarantees these are residue-only
            href = href.lstrip("./")
            if href not in seen:
                seen.add(href)
                css_order.append(href)
        for attrs in SCRIPT_RE.findall(head):
            src_m = SRC_RE.search(attrs)
            if not src_m:
                continue
            src = src_m.group(1)
            if src.startswith(("http:", "https:", "//")):
                continue  # external trackers stay blocked (parity with mirror)
            src = src.lstrip("./")
            if src not in js_seen:
                js_seen.add(src)
                js_order.append({"src": f"static/{src}",
                                 "defer": "defer" in attrs.lower(),
                                 "async": "async" in attrs.lower()})
        for block in STYLE_RE.findall(head):
            key = re.sub(r"\s+", "", block)[:400]
            if key and key not in inline_seen:
                inline_seen.add(key)
                inline_blocks.append(block.strip())

    os.makedirs(f"{module}/static/assets", exist_ok=True)
    with open(f"{module}/static/assets/inline-head.css", "w") as f:
        f.write("\n\n/* ── next inline block ── */\n\n".join(inline_blocks))

    manifest = [f"static/{p}" if not p.startswith("static/") else p for p in css_order]
    manifest.append("static/assets/inline-head.css")
    os.makedirs(f"{module}/src/templates", exist_ok=True)
    with open(f"{module}/src/templates/css-manifest.json", "w") as f:
        json.dump(manifest, f, indent=1)
    with open(f"{module}/src/templates/js-manifest.json", "w") as f:
        json.dump(js_order, f, indent=1)

    # 3. serve static/ from the bundle
    pkg_path = f"{module}/package.json"
    pkg = json.load(open(pkg_path))
    sr = pkg.setdefault("jahia", {}).get("static-resources", "")
    parts = [p.strip() for p in sr.split(",") if p.strip()]
    for need in ("/static/assets", "/static/runtime-assets"):
        if need not in parts:
            parts.append(need)
    pkg["jahia"]["static-resources"] = ",".join(parts)
    with open(pkg_path, "w") as f:
        json.dump(pkg, f, indent=2)
        f.write("\n")

    print(f"[import_assets] {n_assets} asset file(s) -> {module}/static/; "
          f"{len(css_order)} stylesheet(s) + {len(inline_blocks)} inline block(s) "
          f"-> css-manifest.json (ordered)")


if __name__ == "__main__":
    main()
