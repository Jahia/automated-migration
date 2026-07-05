#!/usr/bin/env python3
"""dom_diff — the 0-DOM-change gate (Julian, 2026-07-05).

The target: the migrated page's rendered DOM is STRUCTURALLY IDENTICAL to the
source's visible DOM (tags + attributes + text + order), with zero differing
content nodes. This is stricter and more honest than the pixel gate — it catches
invisible changes (a dropped hidden element, a reordered wrapper) that pixels miss.

Scope (Julian's ruling — "DOM visible, structurel"):
  * runtime-only nodes are stripped from BOTH sides (script / noscript / template /
    style / meta / link / base / head + comments) — Jahia emits no Next.js runtime,
    so comparing those is meaningless; they carry no visible structure.
  * a small set of volatile/hydration attributes is ignored (framework-injected,
    non-semantic) so equal structure isn't flagged as different.
  * Jahia injects NO wrappers into the DOM (Julian) — so there is nothing framework-
    specific to normalize on our side; the render == exactly what our views emit.

Two modes:
  * file A B         — diff two HTML files/strings (used by the reconstruct proxy at
                       the model stage, and by callers that already have both sides).
  * (future) render  — fetch the deployed EDIT render vs the frozen mirror (true gate).

Exit non-zero when differing content nodes exceed the threshold (default 0).
"""
import sys
import re
import argparse
from bs4 import BeautifulSoup, Comment
import difflib

# nodes that never carry VISIBLE structure — stripped from both sides
_RUNTIME_TAGS = {"script", "noscript", "template", "style", "meta", "link", "base",
                 "head", "title"}
# framework-injected / volatile attributes — ignored in the structural signature
# (kept deliberately generic: React/Next hydration ids, ephemeral streaming ids).
_VOLATILE_ATTR = re.compile(
    r"^(data-react|data-reactroot|data-reactid|data-n-|data-hydrate|data-turbo|"
    r"data-astro-|data-svelte|data-v-[0-9a-f]+$|data-server-rendered)", re.I)
# ephemeral id values (Next.js streaming markers B:0 / S:1, react keys)
_EPHEMERAL_ID = re.compile(r"^[BSPF]:[0-9]+$|^:[rR][0-9a-z]+:$")


def _norm_attrs(el):
    out = []
    for k, v in sorted(el.attrs.items()):
        kl = k.lower()
        if _VOLATILE_ATTR.match(kl):
            continue
        if isinstance(v, list):
            v = " ".join(v)
        if kl == "id" and _EPHEMERAL_ID.match(v or ""):
            continue
        # collapse whitespace inside attribute values so re-serialization noise
        # (which is NOT a structural change) doesn't read as a diff
        v = " ".join((v or "").split())
        out.append(f"{kl}={v}")
    return out


def visible_signature(html):
    """Ordered list of per-element signatures for the VISIBLE DOM (document order).
    Each signature = tag + normalized attrs + this element's OWN direct text."""
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup(list(_RUNTIME_TAGS)):
        t.decompose()
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
    sig = []
    for el in soup.find_all(True):
        if el.name in _RUNTIME_TAGS:
            continue
        own_text = " ".join("".join(
            t for t in el.find_all(string=True, recursive=False)).split())
        sig.append("|".join([el.name] + _norm_attrs(el)) +
                   (f"::{own_text}" if own_text else ""))
    return sig


def diff(html_a, html_b):
    """Structural node diff of two DOMs. Returns (differing_nodes, ratio, opcodes,
    sig_a, sig_b). `a` = source (reference), `b` = ours (migrated)."""
    sa, sb = visible_signature(html_a), visible_signature(html_b)
    sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    ops = sm.get_opcodes()
    differing = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in ops if op != "equal")
    return differing, sm.ratio(), ops, sa, sb


def report(html_src, html_ours, label="", threshold=0, show=6):
    differing, ratio, ops, sa, sb = diff(html_src, html_ours)
    print(f"  {label:28s} src_nodes={len(sa):5d} ours_nodes={len(sb):5d} "
          f"struct_sim={ratio * 100:6.2f}%  differing_nodes={differing}")
    shown = 0
    for op, i1, i2, j1, j2 in ops:
        if op == "equal" or shown >= show:
            continue
        shown += 1
        if op == "delete":
            print(f"      − src-only: {sa[i1:i2][:2]}")
        elif op == "insert":
            print(f"      + ours-only: {sb[j1:j2][:2]}")
        else:
            print(f"      ~ src:{sa[i1:i2][:1]}  ours:{sb[j1:j2][:1]}")
    return differing <= threshold, differing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("ours")
    ap.add_argument("--threshold", type=int, default=0)
    a = ap.parse_args()
    src = open(a.src, encoding="utf-8", errors="replace").read()
    ours = open(a.ours, encoding="utf-8", errors="replace").read()
    ok, n = report(src, ours, label="dom_diff", threshold=a.threshold)
    print(f"\n  VERDICT: {'PASS' if ok else 'FAIL'} — {n} differing content node(s) (target ≤ {a.threshold})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
