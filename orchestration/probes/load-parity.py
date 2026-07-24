#!/usr/bin/env python3
"""load-parity.py — the LIVE JCR must wear the load artifact's types.

2026-07-24 (stale-load class): the per-page vision typing fix landed in
orchestration/content/<p>.content-load.json and every FILE-level gate went
green (reconcile, archetype-utilization loaded-distribution) while the SITE
kept running the previous load — home rendered 7/8 bands as sgp:hero although
the artifact says hero/layoutSection/cardGrid/banner/... . A gate that reads
the artifact instead of the site is a proxy gate; this probe closes the class.

It deliberately does NOT re-implement the loader's expectation surface (a
first draft did, and immediately drifted on two skip rules: passthrough
rawHtml naming and chrome-typed footer routing). Instead it runs the loader's
own reconcile in --dry --clean mode — `_expected_main_children` is maintained
in lockstep with the create loop by contract — and PASSES only when every
page's verdict is ALIGNED (deterministic names {type}-{slug}-{idx} match the
EDIT tree, top-level AND nested, missing and surplus both counting). Any
REBUILD verdict = the site does not wear the artifact; the remedy is
re-running load_content --clean for real.

Usage: load-parity.py <project> <site> [locale]
Exit 0 aligned / 1 drift.
"""
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: load-parity.py <project> <site> [locale]")
    project, site = sys.argv[1], sys.argv[2]
    locale = sys.argv[3] if len(sys.argv) > 3 else "en"

    if not os.path.exists(f"{REPO}/orchestration/content/{project}.content-load.json"):
        print("PASS: load-parity — no content-load artifact yet (pre-extract phase)")
        return 0

    r = subprocess.run(
        [sys.executable, f"{REPO}/orchestration/lib/load_content.py",
         project, site, "--clean", "--dry", "--locale", locale],
        capture_output=True, text=True, cwd=REPO)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        print(out[-2000:])
        print("FAIL: load-parity — loader dry-run itself failed", file=sys.stderr)
        return 1

    m = re.search(r"reconcile:\s*(\d+)\s+aligned.*?/\s*(\d+)\s+rebuilt", out)
    if not m:
        print(out[-2000:])
        print("FAIL: load-parity — no reconcile summary in loader output "
              "(a gate that cannot measure must fail)", file=sys.stderr)
        return 1
    aligned, rebuilt = int(m.group(1)), int(m.group(2))
    if rebuilt:
        for line in out.splitlines():
            if "REBUILD" in line:
                print(" ", line.strip())
        print(f"FAIL: load-parity — {rebuilt} page(s) drift from the load "
              f"artifact ({aligned} aligned); re-run load_content --clean",
              file=sys.stderr)
        return 1
    if not aligned:
        print("FAIL: load-parity — 0 pages reconciled (empty artifact or site)",
              file=sys.stderr)
        return 1
    print(f"PASS: load-parity — {aligned} page(s) wear the load artifact's "
          f"types (loader reconcile, EDIT-only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
