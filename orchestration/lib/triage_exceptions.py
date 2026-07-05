#!/usr/bin/env python3
"""triage_exceptions.py — batch PRE-TRIAGE of failing gate/probe exceptions (P5.6).

The end-of-batch exceptions review (gen_plan step_exceptions_review, a scheduled
decision point) asks the assistant to look at every page that did not fit the
frozen profile — potentially dozens of near-identical failures. This script uses
DeepSeek to PRE-DIGEST them into a few failure CLASSES so the assistant's decision
bundle is small and structured, instead of a wall of raw probe output.

This is METADATA about the MIGRATION RUN (a classification of engineering
failures), NOT site content. It never invents or generates any page content.

Inputs (whatever exists — the script degrades gracefully, exit 0 with an empty
triage when there is nothing failing):
  --exceptions <file>   an explicit exceptions report the run dropped (JSON list
                        or {exceptions:[...]}, or newline-delimited text lines).
  integrity-report.json  workflow-output/integrity-report.json — its `mismatches`
                        and any page whose actual/expected instance ratio is low
                        become exception entries (a hollow-page signal).
  --probe-log <file>    a captured stdout/stderr dump from a failing probe
                        (contribution / partition / roundtrip / editor-surface):
                        lines flagged DEAD/PHANTOM/EMPTY/FAIL/MISS become entries.

Classification (one DeepSeek json_object call per batch): each entry ->
  {ref, component, failureClass, scope: "page-specific"|"pattern", summary,
   suggestedAction}. failureClass is a short slug (e.g. "hollow-page",
   "dead-prop", "media-missing", "link-unresolved", "consent-banner",
   "coverage-below-floor"). Entries the model judges the SAME pattern share a
   class so the assistant sees "17 pages, one pattern" not 17 lines.

Output:
  workflow-output/exceptions-triage.json   {classes:[{failureClass, scope, count,
     refs[], components[], summary, suggestedAction}], entries:[...], counts:{}}

Usage:
  python3 orchestration/lib/triage_exceptions.py projects/<p>
      [--exceptions FILE] [--probe-log FILE] [--integrity FILE]
      [--min-ratio 0.5] [--batch-size 40] [--out PATH] [--selftest]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    from . import llm_call  # type: ignore
except Exception:  # noqa: BLE001
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import llm_call  # type: ignore


def _proj_root(project_path: str) -> str:
    p = str(project_path).strip().rstrip("/")
    if "/" not in p and os.sep not in p:
        p = os.path.join("projects", p)
    return p


def _read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


PROBE_FLAG_RE = re.compile(r"\b(DEAD|PHANTOM|EMPTY|FAIL|FAILED|MISS|MISSING|BELOW|ORPHAN)\b", re.I)


def collect_exceptions(project_path: str, *, exceptions_file: str | None,
                       probe_log: str | None, integrity_file: str | None,
                       min_ratio: float) -> list[dict]:
    """Gather exception entries from whatever structured signals exist."""
    entries: list[dict] = []
    wo = os.path.join(_proj_root(project_path), "workflow-output")

    # 1. explicit exceptions report (JSON list / {exceptions:[]} / text lines)
    if exceptions_file and os.path.isfile(exceptions_file):
        try:
            d = _read_json(exceptions_file)
            items = d.get("exceptions", d) if isinstance(d, dict) else d
            for it in (items or []):
                if isinstance(it, dict):
                    entries.append({"source": "exceptions-report",
                                    "ref": it.get("ref") or it.get("page") or it.get("id"),
                                    "component": it.get("component") or it.get("type"),
                                    "text": it.get("message") or json.dumps(it, ensure_ascii=False)})
                else:
                    entries.append({"source": "exceptions-report", "ref": None,
                                    "component": None, "text": str(it)})
        except Exception:  # noqa: BLE001 — not JSON: treat as text lines
            with open(exceptions_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append({"source": "exceptions-report", "ref": None,
                                        "component": None, "text": line})

    # 2. integrity-report mismatches + low instance-ratio pages (hollow pages)
    integ = integrity_file or os.path.join(wo, "integrity-report.json")
    if os.path.isfile(integ):
        try:
            d = _read_json(integ)
        except Exception:  # noqa: BLE001
            d = {}
        for mm in d.get("mismatches", []) or []:
            entries.append({"source": "integrity", "ref": None, "component": None,
                            "text": mm if isinstance(mm, str) else json.dumps(mm, ensure_ascii=False)})
        inst = ((d.get("sections") or {}).get("instances") or {}).get("pages") or {}
        for page, pv in inst.items():
            exp = pv.get("expected")
            act = pv.get("actual_EDIT", pv.get("actual"))
            if exp and act is not None:
                ratio = act / exp if exp else 1.0
                if ratio < min_ratio:
                    entries.append({"source": "integrity", "ref": page, "component": None,
                                    "text": f"page {page}: only {act}/{exp} instances "
                                            f"reached JCR (ratio {ratio:.2f} < {min_ratio})"})

    # 3. captured probe log — flag lines only
    if probe_log and os.path.isfile(probe_log):
        with open(probe_log, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                if PROBE_FLAG_RE.search(line):
                    entries.append({"source": "probe-log", "ref": None,
                                    "component": None, "text": line.strip()[:300]})
    return entries


_SYSTEM = (
    "You triage FAILURES from a website-migration pipeline for a human reviewer. "
    "Each entry is a probe/gate failure (a hollow page, a dead property, a missing "
    "media reference, an unresolved link, a coverage shortfall, a consent-banner "
    "artifact, etc.). Classify each into a SHORT failureClass slug (kebab-case), "
    "decide whether it is 'page-specific' (one page's quirk) or 'pattern' (the "
    "same issue across many pages/components), name the component if the entry "
    "identifies one, and give a one-line summary + a concrete suggestedAction the "
    "reviewer could take (e.g. 'add scope rule exclude-consent-banner', 're-run "
    "load_content for these pages', 'no action — cosmetic'). You classify only — "
    "you never fix, and you never generate any page content. Reply with a single "
    "JSON object, no prose."
)


def _build_user_prompt(batch: list[dict]) -> str:
    payload = [{"i": i, "source": e.get("source"), "ref": e.get("ref"),
                "component": e.get("component"), "detail": e.get("text")}
               for i, e in enumerate(batch)]
    return (
        "ENTRIES:\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n\n"
        'Return JSON: {"triaged":[{"i":<index>,"failureClass":"kebab-slug",'
        '"scope":"page-specific"|"pattern","component":"<name or null>",'
        '"summary":"one line","suggestedAction":"one line"}]}. Cover EVERY index.'
    )


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def triage(project_path: str, entries: list[dict], *, batch_size: int,
           client: "llm_call.LLMClient | None" = None) -> dict:
    if not entries:
        return {"classes": [], "entries": [], "counts": {}, "batches": 0}
    if client is None:
        client = llm_call.LLMClient(project_path=project_path, caller="triage_exceptions.py")

    triaged: dict[int, dict] = {}
    n_batches = 0
    for batch in _chunks(entries, batch_size):
        n_batches += 1
        base = n_batches * 100000  # unique index space per batch is not needed; batch is local
        data = client.chat_json(
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": _build_user_prompt(batch)}],
            temperature=0.0,
            caller=f"triage_exceptions.py:batch{n_batches}",
            meta={"batch": n_batches, "entries": len(batch)},
        )
        offset = (n_batches - 1) * batch_size
        for t in data.get("triaged", []) or []:
            local_i = t.get("i")
            if local_i is None:
                continue
            gi = offset + int(local_i)
            triaged[gi] = {
                "failureClass": (t.get("failureClass") or "unclassified").strip(),
                "scope": (t.get("scope") or "page-specific").strip(),
                "component": t.get("component") or None,
                "summary": (t.get("summary") or "").strip(),
                "suggestedAction": (t.get("suggestedAction") or "").strip(),
            }

    out_entries = []
    classes: dict[str, dict] = {}
    for i, e in enumerate(entries):
        tg = triaged.get(i, {"failureClass": "unclassified", "scope": "page-specific",
                             "component": e.get("component"), "summary": e.get("text", "")[:120],
                             "suggestedAction": ""})
        rec = {**e, **tg}
        out_entries.append(rec)
        cls = classes.setdefault(tg["failureClass"], {
            "failureClass": tg["failureClass"], "scope": tg["scope"],
            "count": 0, "refs": [], "components": set(),
            "summary": tg["summary"], "suggestedAction": tg["suggestedAction"]})
        cls["count"] += 1
        if e.get("ref"):
            cls["refs"].append(e["ref"])
        if tg.get("component"):
            cls["components"].add(tg["component"])
        # a class is a 'pattern' if any member is a pattern
        if tg["scope"] == "pattern":
            cls["scope"] = "pattern"

    class_list = []
    for c in classes.values():
        c["components"] = sorted(c["components"])
        c["refs"] = c["refs"][:50]
        class_list.append(c)
    class_list.sort(key=lambda c: (-c["count"], c["failureClass"]))

    counts = {c["failureClass"]: c["count"] for c in class_list}
    return {"classes": class_list, "entries": out_entries, "counts": counts,
            "batches": n_batches}


# ── selftest ────────────────────────────────────────────────────────
def _selftest() -> int:
    entries = [
        {"source": "integrity", "ref": "en_a", "component": None,
         "text": "page en_a: only 88/125 instances reached JCR (ratio 0.70 < 0.9)"},
        {"source": "integrity", "ref": "en_b", "component": None,
         "text": "page en_b: only 90/126 instances reached JCR (ratio 0.71 < 0.9)"},
        {"source": "probe-log", "ref": None, "component": "asr:heroBanner",
         "text": "DEAD prop asr:heroBanner.body — marker absent from skeleton"},
    ]

    class _Fake:
        def chat_json(self, messages, **kw):
            return {"triaged": [
                {"i": 0, "failureClass": "hollow-page", "scope": "pattern",
                 "component": None, "summary": "low instance ratio",
                 "suggestedAction": "re-run load_content"},
                {"i": 1, "failureClass": "hollow-page", "scope": "pattern",
                 "component": None, "summary": "low instance ratio",
                 "suggestedAction": "re-run load_content"},
                {"i": 2, "failureClass": "dead-prop", "scope": "page-specific",
                 "component": "asr:heroBanner", "summary": "dead body prop",
                 "suggestedAction": "drop prop from CND"},
            ]}

    res = triage("projects/tst", entries, batch_size=40, client=_Fake())
    assert res["counts"].get("hollow-page") == 2, res["counts"]
    assert res["counts"].get("dead-prop") == 1, res["counts"]
    hp = next(c for c in res["classes"] if c["failureClass"] == "hollow-page")
    assert hp["scope"] == "pattern" and set(hp["refs"]) == {"en_a", "en_b"}, hp
    # empty input -> empty triage, no crash
    assert triage("projects/tst", [], batch_size=40, client=_Fake())["classes"] == []
    print("triage_exceptions selftest OK")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?")
    ap.add_argument("--exceptions", default=None, help="explicit exceptions report file")
    ap.add_argument("--probe-log", default=None, help="captured failing-probe stdout/stderr")
    ap.add_argument("--integrity", default=None, help="override integrity-report.json path")
    ap.add_argument("--min-ratio", type=float, default=0.5,
                    help="instance actual/expected below this = a hollow-page entry")
    ap.add_argument("--batch-size", type=int, default=40)
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()
    if not a.project:
        ap.error("project is required (unless --selftest)")

    entries = collect_exceptions(a.project, exceptions_file=a.exceptions,
                                 probe_log=a.probe_log, integrity_file=a.integrity,
                                 min_ratio=a.min_ratio)
    result = triage(a.project, entries, batch_size=a.batch_size)

    wo = os.path.join(_proj_root(a.project), "workflow-output")
    out = a.out or os.path.join(wo, "exceptions-triage.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"project": a.project,
                   "generatedBy": "triage_exceptions.py (run metadata; never site content)",
                   **result}, f, indent=2, ensure_ascii=False)
    print(f"[triage] {len(entries)} exception(s) -> {len(result['classes'])} class(es), "
          f"{result['batches']} LLM batch(es) -> {out}")
    for c in result["classes"]:
        print(f"  [{c['scope']}] {c['failureClass']}: {c['count']} — {c['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
