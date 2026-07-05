#!/usr/bin/env python3
"""contribution.py — G1 static contribution gate (CONTRIBUTION-PLAN P2.5).

Judges the CONTENT-LOAD (what actually reaches the JCR), per page:

  coverage        = lifted editable text chars / visible main-region text chars
                    (both raw and forms-excluded are printed; the gate judges
                    forms-excluded — registered metric refinement: <form>
                    subtrees are script-driven webform widgets, not contributor
                    richtext. No other exclusions.)
  dead props      = a promoted field whose marker is absent from its skeleton
                    (editing it would change nothing), or a CND-declared
                    editable prop on a skeleton type that NO instance lifts
  empty shells    = a typed (promoted) instance with zero wired fields anywhere
  phantom markers = a skeleton marker with no field value (would render empty)

Frozen floors (2026-07-03): coverage >= 60 % min/page, >= 85 % avg.
Exit 0 = PASS, 1 = FAIL.

Usage: contribution.py <project> [--ns NS] [--min 60] [--avg 85]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import semantic_extract as SE  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

MARK_RE = re.compile(r"\{\{f:([^}]+)\}\}")


def text_of(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    # script/style/svg <title>/noscript text is never RENDERED — it must not
    # inflate the visible denominator (observed: 870 chars of SVG titles +
    # inline JS counted as "visible" on the home page).
    for el in soup.find_all(["script", "style", "title", "noscript"]):
        el.extract()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


INTERACTIVE = ["form", "button", "select", "textarea", "video", "iframe"]


def form_text_of(html):
    """Text inside interactive controls — the elements NEVER_IN_BODY refuses
    to lift by design (script-driven widgets: webforms, filter panels,
    carousel controls). Excluded from the G1 denominator, printed separately.
    (Amendment 2026-07-03: extended from <form> only to the NEVER_IN_BODY set —
    same principle, observed live on a Next.js filter panel of <button>s.)"""
    if not html or not any(f"<{t}" in html for t in INTERACTIVE):
        return ""
    soup = BeautifulSoup(html, "lxml")
    seen = []
    for f in soup.find_all(INTERACTIVE):
        f.extract()  # avoid double-count when nested (button inside form)
        seen.append(re.sub(r"\s+", " ", f.get_text(" ", strip=True)))
    return " ".join(x for x in seen if x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", default=None)
    ap.add_argument("--min", type=float, default=60.0)
    ap.add_argument("--avg", type=float, default=85.0)
    a = ap.parse_args()

    load_p = f"orchestration/content/{a.project}.content-load.json"
    data = json.load(open(load_p))
    if data.get("adapter") != "semantic":
        print(f"SKIP: adapter={data.get('adapter')} — contribution gate targets the semantic adapter")
        return 0

    dead, phantoms, shells = [], [], []
    # G5 (phase C, frozen 2026-07-03): media units wired >= 90 %; external
    # residue links wired >= 95 %; internal resolved/unresolved just REPORTED
    g5 = {"mediaWired": 0, "mediaTotal": 0, "mediaNoFile": 0,
          "linkTotal": 0, "linkExtWired": 0,
          "linkIntResolved": 0, "linkIntUnresolved": 0,
          "linkPayloads": 0, "linkPayloadsWired": 0}
    rows = []
    for slug, p in sorted(data.get("pages", {}).items()):
        lifted = visible = formtx = 0
        # P6.3 library containers that carry a verbatim live-splice skeleton:
        # their atoms' markup is INSIDE that skeleton (counting both would
        # double-count the visible text).
        lib_sk = {i for i, _inst in enumerate(p.get("instances", []))
                  if _inst.get("libraryPlan") and _inst.get("skeleton")}
        for idx, inst in enumerate(p.get("instances", [])):
            if inst.get("area"):
                continue
            # NOTE: instances tagged chromeNested (vision-classified chrome nested
            # inline in the content wrapper) stay IN the G1 math for now — on this
            # site they are well-lifted (~94%), and excluding them exposed a vision
            # chrome-misclassification on en_asrp (14.5K chars of real content
            # marked chrome). Metric amendment deferred to a human decision.
            if inst.get("libraryPlan"):
                # P6.3 composable container: fields are intentionally empty (the
                # atoms are separate editable child instances) — never an empty
                # shell. Its optional skeleton is VERBATIM markup (no markers).
                sk = inst.get("skeleton") or ""
                visible += len(text_of(sk))
                formtx += len(form_text_of(sk))
                continue
            if inst.get("libraryAtom"):
                # the atom's editable visible-text surface is its title/label
                # (image weakref + link are editable but carry no visible text);
                # its verbatim markup renders via the container splice when the
                # container has a skeleton, else via the atom itself.
                lifted += len(re.sub(r"\s+", " ", inst.get("atomTitle") or "").strip())
                if inst.get("parent") not in lib_sk:
                    orig = inst.get("imgOrig") or ""
                    visible += len(text_of(orig))
                    formtx += len(form_text_of(orig))
                continue
            if inst.get("promoted") or inst.get("skeleton"):
                # typed skeleton instance OR lifted anonymous raw block (P2.5)
                payloads = [inst] + list(inst.get("children") or [])
                # dead/phantom checks per skeleton (text, media AND link markers)
                for pl in payloads:
                    sk = pl.get("skeleton") or ""
                    marks = set(MARK_RE.findall(sk))
                    flds = set(pl.get("fields") or {})
                    for f in flds - marks:
                        dead.append((slug, inst["type"], f))
                    for mkr in marks - flds:
                        phantoms.append((slug, inst["type"], mkr))
                    med_names = {m["name"] for m in (pl.get("media") or [])}
                    med_marks = set(re.findall(r"\{\{media:([^}]+)\}\}", sk))
                    for mk in med_marks - med_names:
                        phantoms.append((slug, inst["type"], f"media:{mk}"))
                    for mk in med_names - med_marks:
                        dead.append((slug, inst["type"], f"media:{mk}"))
                    if "{{link:href}}" in sk and not pl.get("link"):
                        phantoms.append((slug, inst["type"], "link:href"))
                    # G5 accounting
                    g5["mediaWired"] += len(med_names)
                    # lift_media caps at 16 images per scope — images beyond
                    # that stay verbatim in the skeleton (no markers, render
                    # correctly). Cap the denominator to match.
                    _cap = 16
                    g5["mediaTotal"] += max(min(pl.get("mediaTotal", 0), _cap), len(med_names))
                    for m in pl.get("media") or []:
                        if not os.path.isfile(f"projects/{a.project}/workflow-output/"
                                              f"local-mirror/assets/{m.get('file', '')}"):
                            g5["mediaNoFile"] += 1
                    lnk = pl.get("link")
                    tot = max(pl.get("linkTotal", 0), 1 if lnk else 0)
                    g5["linkTotal"] += tot
                    if tot:
                        g5["linkPayloads"] += 1
                    if lnk:
                        g5["linkPayloadsWired"] += 1
                    if lnk:
                        h = lnk.get("href", "")
                        if h.startswith(("http://", "https://", "//", "mailto:", "tel:")):
                            g5["linkExtWired"] += 1
                        else:
                            slugp = h.split("?")[0].split("#")[0].strip("/").replace("/", "_") or "home"
                            g5["linkIntResolved" if slugp in data.get("pages", {})
                               else "linkIntUnresolved"] += 1
                # a {{child:N}} container's typed children are SEPARATE
                # parent-linked instances (emit_container_live) — a container
                # whose content lives in those children is not an empty shell.
                child_content = any(
                    o.get("parent") == idx and (
                        o.get("fields") or o.get("media") or o.get("link")
                        or o.get("libraryPlan") or o.get("libraryAtom"))
                    for o in p.get("instances", []))
                if inst.get("promoted") and not child_content and not any(
                        pl.get("fields") or pl.get("media") or pl.get("link")
                        for pl in payloads):
                    shells.append((slug, inst["type"]))
                recomposed = SE.recompose_group(
                    inst.get("skeleton") or "", inst.get("fields") or {},
                    inst.get("children") or [],
                    media=inst.get("media"), link=inst.get("link"))
                visible += len(text_of(recomposed))
                formtx += len(form_text_of(recomposed))
                for pl in payloads:
                    for k, v in (pl.get("fields") or {}).items():
                        lifted += len(text_of(v)) if k.startswith("body") else len(v)
            elif inst.get("passthrough"):
                h = (inst.get("fields") or {}).get("html", "")
                visible += len(text_of(h))
                formtx += len(form_text_of(h))
        denom = max(visible - formtx, 1)
        rows.append({"slug": slug, "visible": visible, "form": formtx,
                     "lifted": lifted,
                     "raw": 100.0 * lifted / max(visible, 1),
                     "xform": min(100.0, 100.0 * lifted / denom)})

    print(f"{'page':58s} {'raw%':>6s} {'noform%':>8s}  lifted/visible (form)")
    for r in rows:
        print(f"{r['slug']:58s} {r['raw']:6.1f} {r['xform']:8.1f}  "
              f"{r['lifted']}/{r['visible']} ({r['form']})")

    xs = [r["xform"] for r in rows]
    mn, avg = (min(xs), sum(xs) / len(xs)) if xs else (0, 0)
    print(f"\ncontribution coverage (forms-excluded): min={mn:.1f}% avg={avg:.1f}% "
          f"(floors: min>={a.min:.0f}, avg>={a.avg:.0f})")
    print(f"dead props={len(dead)}  phantom markers={len(phantoms)}  empty shells={len(shells)}")
    for lbl, lst in (("dead", dead), ("phantom", phantoms), ("shell", shells)):
        for x in lst[:5]:
            print(f"  ✗ {lbl}: {x}")

    ok = (mn >= a.min and avg >= a.avg
          and not dead and not phantoms and not shells)
    print(("PASS" if ok else "FAIL") + ": G1 contribution gate")

    # G5 media/link wiring (phase C)
    mt = g5["mediaTotal"]
    media_pct = 100.0 * g5["mediaWired"] / mt if mt else 100.0
    lp = g5["linkPayloads"]
    link_pct = 100.0 * g5["linkPayloadsWired"] / lp if lp else 100.0
    print(f"\nG5 media: {g5['mediaWired']}/{mt} units wired ({media_pct:.1f}%, floor 90) "
          f"— missing mirror files: {g5['mediaNoFile']}")
    print(f"G5 links: {g5['linkPayloadsWired']}/{lp} link-bearing payloads wired "
          f"({link_pct:.1f}%, floor 95) — external {g5['linkExtWired']}, internal "
          f"resolved {g5['linkIntResolved']}, unresolved (verbatim fallback) "
          f"{g5['linkIntUnresolved']}; residue anchors total {g5['linkTotal']}")
    ok5 = media_pct >= 90.0 and link_pct >= 95.0
    print(("PASS" if ok5 else "FAIL") + ": G5 media/link wiring gate")
    return 0 if (ok and ok5) else 1


if __name__ == "__main__":
    sys.exit(main())
