#!/usr/bin/env python3
"""component_coverage.py — component-model gate (doctrine 2026-07-06).

Pixel fidelity proves nothing about the component model, and G1 proves only
that TEXT is editable — a page can pass both as one giant editable rawHtml
fragment ("fragment soup", observed on discoverasr: the page-specific content
of every unsegmented page loaded as a single 68K-char anonymous blob). This
gate makes that shape impossible:

Per page, over the content-load payload (the exact artifact load_content
writes; the integrity belt + G6 verify payload -> JCR faithfulness):

  typedShare  = visible text chars owned by TYPED instances (a vision-named
                nodeType: promoted non-rawHtml, or a library plan/atom)
                / ALL visible main-region text chars.
                Anonymous shapes — container wrappers (promoted rawHtml),
                lifted-but-untyped skeletons, verbatim passthrough — all count
                against the share: wrapper markup must stay thin and content
                must live in named components.
  fragments   = non-typed instances carrying >= --max-fragment (200) visible
                text chars. Each is a content block the editor cannot address
                as a component. The gate requires ZERO.

FROZEN floors (2026-07-06): typedShare >= 80 % min/page, >= 90 % avg,
0 oversized anonymous fragments. Exit 0 = PASS, 1 = FAIL.

Usage: component_coverage.py <project> [--min 80] [--avg 90] [--max-fragment 200]
"""
import argparse
import json
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 2)[0] + "/lib")
from bs4 import BeautifulSoup  # noqa: E402

MARK_RE = re.compile(r"\{\{(?:f|child|media|link):[^}]*\}\}")


def visible_text(html):
    """Rendered text of a markup chunk — script/style/svg-title/noscript are
    never rendered (same exclusions as contribution.py's text_of)."""
    if not html or "<" not in html:
        return re.sub(r"\s+", " ", (html or "").strip())
    soup = BeautifulSoup(html, "lxml")
    for el in soup.find_all(["script", "style", "title", "noscript"]):
        el.extract()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def instance_visible_chars(inst):
    """Visible text an instance OWNS: its skeleton markup (markers stripped —
    children/fields are counted on their own instances) + its own field values
    + verbatim html."""
    total = 0
    sk = inst.get("skeleton") or ""
    if sk:
        total += len(visible_text(MARK_RE.sub(" ", sk)))
    for v in (inst.get("fields") or {}).values():
        if isinstance(v, str):
            total += len(visible_text(v))
    return total


def is_typed(inst):
    """A typed instance = the editor sees a NAMED component, not 'Raw HTML'."""
    if inst.get("libraryPlan") or inst.get("libraryAtom"):
        return True
    return bool(inst.get("promoted")) and inst.get("type") not in (None, "rawHtml")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--min", type=float, default=80.0)
    ap.add_argument("--avg", type=float, default=90.0)
    ap.add_argument("--max-fragment", type=int, default=200)
    a = ap.parse_args()

    load_p = f"orchestration/content/{a.project}.content-load.json"
    data = json.load(open(load_p))
    if data.get("adapter") != "semantic":
        print(f"SKIP: adapter={data.get('adapter')} — component gate targets the semantic adapter")
        return 0

    rows, all_fragments = [], []
    for slug, p in sorted(data.get("pages", {}).items()):
        insts = p.get("instances", [])
        # library containers carry a verbatim live-splice skeleton — their
        # atoms' text is INSIDE it; skip the atoms to avoid double-count.
        lib_parent = {i for i, x in enumerate(insts)
                      if x.get("libraryPlan") and x.get("skeleton")}
        typed = anon = 0
        frags = []
        for idx, inst in enumerate(insts):
            if inst.get("area"):
                continue          # chrome singletons live outside the page
            if inst.get("parent") in lib_parent and inst.get("libraryAtom"):
                continue
            n = instance_visible_chars(inst)
            if n == 0:
                continue
            if is_typed(inst):
                typed += n
            else:
                anon += n
                if n >= a.max_fragment:
                    frags.append((idx, inst.get("type"), n))
        total = typed + anon
        share = 100.0 * typed / total if total else 100.0
        rows.append((slug, share, typed, anon, len(frags)))
        for idx, t, n in frags:
            all_fragments.append((slug, idx, t, n))

    if not rows:
        print("FAIL: no pages in the content-load payload")
        return 1
    mn = min(r[1] for r in rows)
    avg = sum(r[1] for r in rows) / len(rows)

    print(f"=== COMPONENT COVERAGE — {a.project} "
          f"(floors: min {a.min}%, avg {a.avg}%, 0 fragments >= {a.max_fragment} chars) ===")
    print(f"{'page':32s} {'typed%':>7s} {'typed':>8s} {'anon':>8s} {'frags':>6s}")
    for slug, share, typed, anon, nf in rows:
        flag = "" if share >= a.min and nf == 0 else "  <-- "
        print(f"{slug:32s} {share:6.1f}% {typed:8d} {anon:8d} {nf:6d}{flag}")
    print(f"\n  min {mn:.1f}%  avg {avg:.1f}%  anonymous fragments {len(all_fragments)}")
    for slug, idx, t, n in all_fragments[:15]:
        print(f"    fragment: {slug}[{idx}] type={t} {n} visible chars")
    if len(all_fragments) > 15:
        print(f"    ... and {len(all_fragments) - 15} more")

    ok = mn >= a.min and avg >= a.avg and not all_fragments
    print(f"  gate: {'GREEN' if ok else 'RED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
