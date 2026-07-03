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
     "rulesWithZeroMatches": [ids], "flagged": [pages], "rules": [ids]}

FROZEN constants: charShare flag threshold = 0.20; shareBasis = "chars".
"""

import json
import shutil
import sys
from pathlib import Path

from bs4 import BeautifulSoup

FLAG_SHARE = 0.20  # frozen — pages above this excluded-char share are flagged


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

    Returns (report_dict, expected: {relpath: bytes-or-None}).
    expected values are None for pass-through (non-HTML) files, meaning
    "must equal prescope bytes".
    """
    mirror = pp / "workflow-output" / "local-mirror"
    prescope = pp / "workflow-output" / "local-mirror-prescope"

    pages = []
    rule_ids = [r["id"] for r in rules]
    matched_any = {rid: 0 for rid in rule_ids}
    flagged = []
    expected = {}

    for src in sorted(prescope.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(prescope)
        dst = mirror / rel
        raw = src.read_bytes()
        if src.suffix.lower() in (".html", ".htm"):
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
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(out)

    report = {
        "shareBasis": "chars",
        "pages": pages,
        "rulesWithZeroMatches": [rid for rid in rule_ids if not matched_any.get(rid)],
        "flagged": flagged,
        "rules": rule_ids,
    }
    return report, expected


def empty_report():
    return {"shareBasis": "chars", "pages": [], "rulesWithZeroMatches": [],
            "flagged": [], "rules": []}


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

    report, expected = build(pp, rules, write=not check)

    if check:
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

    report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    n_pages = len(report["pages"])
    n_matched = sum(1 for p in report["pages"] if p["matches"])
    print(f"scope_apply: {len(rules)} rule(s) applied over {n_pages} page(s); "
          f"{n_matched} page(s) matched; flagged>{FLAG_SHARE:.0%}: {report['flagged'] or 'none'}; "
          f"zero-match rules: {report['rulesWithZeroMatches'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
