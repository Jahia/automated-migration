#!/usr/bin/env python3
"""scope_apply.py — apply scope rules to the local mirror (ASSIST-PLAN §5).

The local mirror at <PP>/workflow-output/local-mirror/ becomes the SCOPED
reference every downstream step consumes.

Design (frozen invariants):
- First run snapshots local-mirror -> local-mirror-prescope (only if absent).
- EVERY run rebuilds each HTML page FROM the prescope copy + current rules,
  so rules never compound (idempotent by construction).
- Pages with ZERO rule matches are copied from prescope BYTE-IDENTICAL
  (never re-serialized). Non-HTML assets copied through untouched.
- Parser: lxml + plain str(soup), same conventions as localize_site.py.

Usage:
    python3 orchestration/lib/scope_apply.py <PP>          # apply
    python3 orchestration/lib/scope_apply.py <PP> --check  # verify (PROBE)

<PP> like projects/discoverasr, cwd = repo root.

Rules file <PP>/workflow-output/scope-rules.json:
    {"rules": [{"id": "...", "action": "exclude"|"force_passthrough",
                "match": {"selector": "<css>"}, "scope": "site",
                "reason": "...", "decidedBy": "...", "date": "YYYY-MM-DD"}]}

Report <PP>/workflow-output/scope-report.json:
    {"shareBasis": "chars",
     "pages": [{"page": "...", "matches": {ruleId: n}, "removedChars": n,
                "totalChars": n, "charShare": 0.03}],
     "rulesWithZeroMatches": [ids], "flagged": [pages], "rules": [ids],
     "invalidated": [slugs]}

Segment-artifact invalidation (this tool owns the scoped DOM, so it owns the
freshness of everything keyed off it): on APPLY, any mirror HTML page whose
scoped bytes CHANGED versus what the file held before this invocation has its
per-page segmentation artifacts deleted, because segment_probe.mjs runs
incrementally and would otherwise skip a page whose green segmentation was
measured on the pre-change DOM. Deleted per changed slug (only if present):
  segment/<slug>.segmentation.json, .dom.html, .segmap.html, .page.png
  segment/adjudication/<slug>.json
Slug = the mirror-relative path minus its .html/.htm suffix — exactly the
identity segment_probe.mjs serves as `<slug>.html`. Pages whose bytes did NOT
change keep their artifacts (identical DOM → still-valid greens). The changed
slugs are reported in scope-report.json "invalidated". --check never deletes.

FROZEN constants: charShare flag threshold = 0.20; shareBasis = "chars".
"""

import json
import shutil
import sys
from pathlib import Path

from bs4 import BeautifulSoup

FLAG_SHARE = 0.20  # frozen — pages above this excluded-char share are flagged

# Per-page segment artifacts keyed by slug (see segment_probe.mjs writes).
SEGMENT_SUFFIXES = (".segmentation.json", ".dom.html", ".segmap.html", ".page.png")


def slug_for(rel: Path) -> str:
    """Mirror-relative HTML path -> segment slug.

    Identical to segment_probe.mjs's convention: it serves each page as
    `<slug>.html` (line `page.goto(`${base}/${slug}.html`)`) and the mirror
    files are flat, so the slug is the relative path with its .html/.htm
    suffix stripped (POSIX separators, matching page-inventory slugs like
    `en`, `en_adoor-apartment`).
    """
    return rel.with_suffix("").as_posix()


def invalidate_segments(pp: Path, slugs):
    """Delete the per-page segment artifacts for the given changed slugs.

    Only removes files that exist; a missing segment dir means there is
    nothing to do. Also prunes adjudication/<slug>.json (an adjudication of a
    changed DOM is stale). Returns the sorted, de-duplicated slug list — the
    set of pages whose scoped DOM changed and must therefore be re-segmented
    (recorded even when no artifact was on disk yet).
    """
    seg = pp / "workflow-output" / "segment"
    for slug in slugs:
        for suffix in SEGMENT_SUFFIXES:
            f = seg / f"{slug}{suffix}"
            if f.is_file():
                f.unlink()
        adj = seg / "adjudication" / f"{slug}.json"
        if adj.is_file():
            adj.unlink()
    return sorted(set(slugs))


def load_rules(pp: Path):
    rules_file = pp / "workflow-output" / "scope-rules.json"
    if not rules_file.exists():
        return []
    data = json.loads(rules_file.read_text(encoding="utf-8"))
    return data.get("rules") or []


def apply_rules_to_html(raw: bytes, rules):
    """Returns (out_bytes, matches{ruleId:count}, removed_chars, total_chars).

    Zero total matches -> out_bytes is the input, byte-identical.
    """
    soup = BeautifulSoup(raw, "lxml")
    total_chars = len(soup.get_text())
    matches = {}
    removed_chars = 0
    any_match = False
    for rule in rules:
        selector = (rule.get("match") or {}).get("selector")
        if not selector:
            continue  # signature-based matching not implemented yet
        els = soup.select(selector)
        matches[rule["id"]] = len(els)
        if not els:
            continue
        any_match = True
        action = rule.get("action")
        for el in els:
            if action == "exclude":
                removed_chars += len(el.get_text())
                el.decompose()
            elif action == "force_passthrough":
                el["data-scope-passthrough"] = rule["id"]
    if not any_match:
        return raw, matches, 0, total_chars
    return str(soup).encode("utf-8"), matches, removed_chars, total_chars


def build(pp: Path, rules, write: bool):
    """Compute (and optionally write) the scoped mirror from prescope + rules.

    Returns (report_dict, expected: {relpath: bytes-or-None}, changed_slugs).
    expected values are None for pass-through (non-HTML) files, meaning
    "must equal prescope bytes".
    changed_slugs = slugs of HTML pages whose scoped bytes differ from what
    the mirror file held BEFORE this invocation (empty when write=False —
    --check computes but never mutates or invalidates).
    """
    mirror = pp / "workflow-output" / "local-mirror"
    prescope = pp / "workflow-output" / "local-mirror-prescope"

    pages = []
    rule_ids = [r["id"] for r in rules]
    matched_any = {rid: 0 for rid in rule_ids}
    flagged = []
    expected = {}
    changed_slugs = []

    for src in sorted(prescope.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(prescope)
        dst = mirror / rel
        raw = src.read_bytes()
        is_html = src.suffix.lower() in (".html", ".htm")
        if is_html:
            out, matches, removed, total = apply_rules_to_html(raw, rules)
            for rid, n in matches.items():
                matched_any[rid] = matched_any.get(rid, 0) + n
            share = round(removed / total, 4) if total else 0.0
            pages.append({
                "page": str(rel),
                "matches": {rid: n for rid, n in matches.items() if n},
                "removedChars": removed,
                "totalChars": total,
                "charShare": share,
            })
            if share > FLAG_SHARE:
                flagged.append(str(rel))
        else:
            out = raw
        expected[str(rel)] = out
        if write:
            # A page's segment artifacts are stale iff its scoped bytes change
            # vs what the mirror held before this write. Capture BEFORE writing.
            if is_html:
                prev = dst.read_bytes() if dst.is_file() else None
                if prev != out:
                    changed_slugs.append(slug_for(rel))
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(out)

    report = {
        "shareBasis": "chars",
        "pages": pages,
        "rulesWithZeroMatches": [rid for rid in rule_ids if not matched_any.get(rid)],
        "flagged": flagged,
        "rules": rule_ids,
    }
    return report, expected, changed_slugs


def empty_report():
    return {"shareBasis": "chars", "pages": [], "rulesWithZeroMatches": [],
            "flagged": [], "rules": [], "invalidated": []}


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    check = "--check" in argv
    if len(args) != 1:
        print("usage: scope_apply.py <projects/NAME> [--check]", file=sys.stderr)
        return 2
    pp = Path(args[0])
    wo = pp / "workflow-output"
    mirror = wo / "local-mirror"
    prescope = wo / "local-mirror-prescope"
    report_file = wo / "scope-report.json"

    if not mirror.is_dir():
        print(f"scope_apply: no local mirror at {mirror}", file=sys.stderr)
        return 2

    rules = load_rules(pp)

    if not rules:
        if check:
            # No rules: consistent iff mirror equals prescope (when one exists).
            if not prescope.is_dir():
                print("scope_apply --check: no rules, no prescope — OK")
                return 0
            for src in sorted(prescope.rglob("*")):
                if not src.is_file():
                    continue
                rel = src.relative_to(prescope)
                dst = mirror / rel
                if not dst.is_file() or dst.read_bytes() != src.read_bytes():
                    print(f"scope_apply --check: FAIL {rel} differs from prescope (no rules in force)")
                    return 1
            print("scope_apply --check: no rules, mirror == prescope — OK")
            return 0
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(empty_report(), indent=2) + "\n", encoding="utf-8")
        print("scope_apply: no rules in force — empty report written, mirror untouched")
        return 0

    # Snapshot once: the prescope is the immutable pre-rules reference.
    if not prescope.is_dir():
        if check:
            print("scope_apply --check: FAIL rules exist but no prescope snapshot (apply never ran)")
            return 1
        shutil.copytree(mirror, prescope)
        print(f"scope_apply: snapshotted {mirror} -> {prescope}")

    report, expected, changed_slugs = build(pp, rules, write=not check)

    if check:
        # Read-only: never mutate the mirror or invalidate segment artifacts.
        bad = []
        for rel, out in expected.items():
            dst = mirror / rel
            if not dst.is_file() or dst.read_bytes() != out:
                bad.append(rel)
        if bad:
            print(f"scope_apply --check: FAIL {len(bad)} file(s) inconsistent with prescope+rules: "
                  + ", ".join(bad[:10]))
            return 1
        print(f"scope_apply --check: OK — {len(expected)} files consistent with prescope+rules")
        return 0

    # Only pages whose scoped DOM actually changed lose their (now-stale)
    # segment artifacts; byte-identical pages keep their green segmentations.
    invalidated = invalidate_segments(pp, changed_slugs)
    report["invalidated"] = invalidated

    report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    n_pages = len(report["pages"])
    n_matched = sum(1 for p in report["pages"] if p["matches"])
    print(f"scope_apply: {len(rules)} rule(s) applied over {n_pages} page(s); "
          f"{n_matched} page(s) matched; flagged>{FLAG_SHARE:.0%}: {report['flagged'] or 'none'}; "
          f"zero-match rules: {report['rulesWithZeroMatches'] or 'none'}; "
          f"invalidated segments: {invalidated or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
