#!/usr/bin/env python3
"""Compare local fingerprints vs reference fingerprints -> fidelity punch-list.
Local: produced by local_fingerprint.py (stdin or path arg 1).
Reference: orchestration/audit/reference_fp_<project>.json (browser-captured).
Writes a ranked Markdown punch-list to projects/<project>/workflow-output/audit/FIDELITY.md.
Usage: python3 orchestration/audit/audit_compare.py <project> <local_fp.json>
"""
import sys, json, os
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "sial-paris"
local = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "/tmp/local_fp.json"))
ref = json.load(open(f"orchestration/audit/reference_fp_{PROJECT}.json"))

rows = []
for path, lf in local.items():
    rf = ref.get(path)
    lt = lf.get("text_len", 0); li = lf.get("imgs", 0)
    if path.startswith("exposer"):
        rows.append((0, path, "N/A-NEW", lt, "-", li, "-", "net-new section, no reference")); continue
    if not rf:
        rows.append((0, path, "N/A", lt, "?", li, "?", "no reference fingerprint captured")); continue
    if "error" in rf:
        rows.append((0, path, "N/A-REF", lt, "err", li, "-", "reference page errors (HTTP 500)")); continue
    rt = rf["t"]; ri = rf["i"]
    ratio = (lt / rt) if rt else 99
    if rt < 120 and lt > 400:
        sev = 3; cls = "FABRICATED"; note = f"reference is an empty hero-only page ({rt} chars); local invents {lt} chars of content"
    elif rt >= 400 and ratio < 0.35:
        sev = 3; cls = "STUB"; note = f"local is a thin stub: {lt} vs {rt} chars on reference (×{ratio:.2f})"
    elif rt >= 400 and ratio < 0.6:
        sev = 2; cls = "THIN"; note = f"local thinner than reference: {lt} vs {rt} chars (×{ratio:.2f})"
    elif ri - li >= 8:
        sev = 2; cls = "MISSING-IMG"; note = f"reference has {ri} images, local has {li}"
    elif 0.6 <= ratio <= 1.8 and abs(ri - li) <= 6:
        sev = 0; cls = "OK"; note = f"comparable ({lt} vs {rt} chars, {li} vs {ri} imgs)"
    else:
        sev = 1; cls = "REVIEW"; note = f"{lt} vs {rt} chars (×{ratio:.2f}), {li} vs {ri} imgs"
    rows.append((sev, path, cls, lt, rt, li, ri, note))

rows.sort(key=lambda r: (-r[0], r[1]))
out = ["# Fidelity audit - local render vs reference (sialparis.com)", "",
       "Signal = `<main>` body text length + image count (proxy for content parity). "
       "Reference captured via browser; local via Jahia live render.", "",
       "| sev | page | class | local txt | ref txt | local img | ref img | finding |",
       "|----|------|-------|----:|----:|----:|----:|--------|"]
sevn = {3:"🔴", 2:"🟠", 1:"🟡", 0:"🟢"}
counts = {}
for sev, path, cls, lt, rt, li, ri, note in rows:
    counts[cls] = counts.get(cls, 0) + 1
    out.append(f"| {sevn.get(sev,'')} | `{path}` | {cls} | {lt} | {rt} | {li} | {ri} | {note} |")
out += ["", "## Summary", ""]
for cls, n in sorted(counts.items(), key=lambda x: -x[1]):
    out.append(f"- **{cls}**: {n}")
md = "\n".join(out) + "\n"
d = f"projects/{PROJECT}/workflow-output/audit"
os.makedirs(d, exist_ok=True)
open(f"{d}/FIDELITY.md", "w", encoding="utf-8").write(md)
print(md)
print(f"\nwritten: {d}/FIDELITY.md")
