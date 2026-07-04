#!/usr/bin/env python3
"""decompose_logowall.py — P6.2 PROTOTYPE: recursive structural decomposition of
the discoverasr brands-logo wall onto the base component library.

This is the recompose-stage logic Julian asked to PROVE end-to-end on ONE section
(MODULARITY-PLAN §6 step 3 / DECOMP-PROTOTYPE). It is a targeted prototype, NOT
the generic recursive `group` stage — that generalization comes after the loop
is proven.

Recognizer (deterministic, structural — never content generation):
  a wrapper whose repeated same-signature children (>=3) each wrap a media/link
  → a container ($NS:logoWall) of typed atoms ($NS:logo);
  the odd-one-out with its own class (a.master-logo) → a fixed named slot `master`.

Fidelity-first (locked §5b): every atom carries the SOURCE markup facts so the
promoted view reproduces the source classes/structure (skinning) — the composed
render is byte-identical to the frozen skeleton when unedited.

Input:  projects/<proj>/workflow-output/html-fragments/brands-logo-section.html
Output: a decomposition record (JSON) describing:
  - the $NS:logoWall container node (heading empty — source has none)
  - master  = one $NS:logo (fixed slot)
  - logos   = N $NS:logo children (open repeater)
  each logo: image file (-> DAM weakref), imageAltText, link href (-> j:linkType),
  variant (master|brand), breakClass (the responsive break-* spacer that FOLLOWS
  this logo in source, kept so flex-wrap breakpoints survive), title attr.

Usage: decompose_logowall.py <project> [--ns asr] [--out PATH]
"""
import argparse
import json
import os
import re
import sys

from bs4 import BeautifulSoup

# spacer <div> classes that force a flex line break at a breakpoint (load-bearing
# layout — flex-basis:100%). A classless <div> spacer has NO css and is dropped.
BREAK_CLASSES = {"break-mobile", "break-tablet", "break-desktop"}


def img_facts(anchor, project):
    """Extract the fidelity facts from a logo <a><picture><img></a>."""
    img = anchor.find("img")
    if not img:
        return None
    src = img.get("src", "")
    file = os.path.basename(src) if src else ""
    # Rewrite the captured relative src (`assets/x.svg`) to the module-absolute
    # form the Jahia render serves (`/modules/<proj>/static/assets/x.svg`) — the
    # verbatim <picture> is rendered as-is by the view, so its src MUST resolve
    # under Jahia (a bare `assets/` path 404s). Matches the source content-load
    # media[].orig convention.
    if file:
        img["src"] = f"/modules/{project}/static/assets/{file}"
    return {
        "file": file,
        "alt": img.get("alt", ""),
        "title": img.get("title", "") or "",
        # exact <picture> markup, module-absolute src (the verbatim-default
        # contract, rule 26 — stored so an unedited node is byte-exact).
        "orig": str(anchor.find("picture")),
        "href": anchor.get("href", ""),
        "ariaLabel": anchor.get("aria-label", ""),
    }


def decompose(fragment_html, ns="asr", project="discoverasr"):
    soup = BeautifulSoup(fragment_html, "html.parser")
    section = soup.select_one(".asr-section-brands-logo")
    if not section:
        sys.exit("FAIL: no .asr-section-brands-logo in fragment")

    master_a = section.select_one("a.master-logo")
    wrapper = section.select_one(".logos-wrapper")
    if not master_a or not wrapper:
        sys.exit("FAIL: master-logo or logos-wrapper missing")

    # walk logos-wrapper direct children in document order: each brand-logo
    # anchor becomes a logo child; a break-* div that FOLLOWS an anchor is
    # recorded on that anchor's atom (so the breakpoint travels with the logo).
    logos = []
    pending = None
    for ch in wrapper.find_all(recursive=False):
        if ch.name == "a" and "brand-logo" in (ch.get("class") or []):
            pending = img_facts(ch, project)
            pending["variant"] = "brand"
            pending["breakClass"] = ""
            logos.append(pending)
        elif ch.name == "div":
            cls = [c for c in (ch.get("class") or []) if c in BREAK_CLASSES]
            if cls and pending is not None:
                pending["breakClass"] = " ".join(cls)
            # classless spacer divs: pure serialization artifact, dropped

    master = img_facts(master_a, project)
    master["variant"] = "master"
    master["breakClass"] = ""

    return {
        "container": {
            "type": "logoWall",
            "nodeType": f"{ns}:logoWall",
            # source section carries no heading text
            "heading": "",
            # extra classes on .logo-container beyond the base ('wrap' here) —
            # kept so the view reproduces them (fidelity)
            "logoContainerClass": " ".join(
                section.select_one(".logo-container").get("class") or []
            ),
        },
        "master": master,
        "logos": logos,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", default="asr")
    ap.add_argument("--out")
    a = ap.parse_args()

    frag = (
        f"projects/{a.project}/workflow-output/html-fragments/brands-logo-section.html"
    )
    if not os.path.isfile(frag):
        sys.exit(f"FAIL: fragment not found: {frag}")
    rec = decompose(open(frag, encoding="utf-8").read(), a.ns, a.project)

    out = a.out or f"orchestration/content/{a.project}.logowall.decomp.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(rec, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    n = len(rec["logos"])
    print(f"[decompose_logowall] {a.project} ns={a.ns} -> {out}")
    print(f"  container: {rec['container']['nodeType']} "
          f"(logo-container class={rec['container']['logoContainerClass']!r})")
    print(f"  master slot: {rec['master']['file']} alt={rec['master']['alt']!r}")
    print(f"  {n} brand logos (open repeater); "
          f"{sum(1 for l in rec['logos'] if l['breakClass'])} carry a break-* spacer")
    print(f"  total logos = {n + 1} (1 master + {n} brand) — vs 1 frozen node today")


if __name__ == "__main__":
    main()
