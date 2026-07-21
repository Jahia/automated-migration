#!/usr/bin/env python3
"""publish_site.py — the SINGLE FINAL PUBLICATION act (Julian doctrine 2026-07-04).

The migration process is EDIT-only: load_content, the reconcile verdicts and the
in-process probes never publish ("retire toute forme de publication de ton
process, ça alourdit. Je publierai à la fin quand tout sera fini."). A stale
LIVE is tolerated the whole way; THIS command, run once by Julian at the end
(via orchestration/assist/publish_site.sh), reconciles LIVE with EDIT and then
proves it with the strict integrity belt.

WHY UNPUBLISH-FIRST (evidence measured live on discoverasr, 2026-07-04):
  * publish alone — parent, includeSubTree, or per-child — NO-OPS in 1 ms on a
    divergent area: the EDIT-side publication metadata is corrupted
    (aggregatedPublicationInfo claims PUBLISHED while LIVE is stale/absent), so
    the SUCCESSFUL scheduler job publishes NOTHING (durationMs:1, 18 005 jobs
    on the counter). Publishing harder never repairs.
  * Jahia preserves UUIDs across publishes and NEVER reassigns them — a LIVE
    node with a stale uuid (from a delete/recreate cycle in EDIT) can never be
    re-aligned by any publish; the LIVE copy must be PURGED first.
  * publication.unpublish ignores the corrupted state, purges LIVE instantly
    (<1 s measured) and RESETS the metadata; the publish that follows then
    REALLY runs (publishedNodeCount:85, finished:true)...
  * ...but LIVE propagation TRICKLES past the return: 1 child visible at
    t+180 s, 84/84 aligned at t+200 s. Hence the ~300 s alignment budget, and
    the poll only concludes on FULL (name,uuid) equality — never on a first
    partial count.
  Recipe proven end-to-end on en_adoor-apartment: unpublish → LIVE empty <1 s
  → publish → 84/84 aligned, 0 mismatch. (Sequence moved here from
  load_content._publish_until_aligned, commit 264cd1a — the load is EDIT-only.)

TARGETS, in order (all derived from the content-load plan, no per-project logic):
  1. /sites/<site>/files — DAM first: weakref targets must resolve in LIVE
     before the pages that reference them. Plain publish (no unpublish-first):
     DAM files are upload-once, never delete/recreate, so their uuids never
     diverge; the final belt's LIVE media count is the check.
  2. chrome areas (/sites/<site>/home/<area>) — from the plan's area-flagged
     instances (header/footer/nav...), unpublish-first, alignment-verified.
  3. every page of the plan — the page NODE subtree (covers main area + shell
     + translations), unpublish-first, verified by main-area (name,uuid)
     alignment. GUARD: a "home" slug targets its /main area (+ shell) only,
     NEVER the /home node — includeSubTree on /home would unpublish and
     republish the ENTIRE site through one fragile cycle.

Idempotent and re-launchable: an already-aligned target is verified and
skipped, a failed target does not stop the others (publish as much as possible,
report everything). At the end the strict belt runs:
  integrity.py <projects/project> <site> --phase step_publish_final
and this command exits with its code (or 1 if any target failed).

Usage:
  python3 orchestration/lib/publish_site.py <project> <site> [--locale en] [--dry]
  orchestration/assist/publish_site.sh <project> <site> [locale]
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(REPO_ROOT)  # Loader artifacts are repo-root-relative
from load_content import Loader  # noqa: E402  (shared readers, plan, MCP client)

PURGE_POLL_S = 60      # unpublish is <1 s measured; margin under load
ALIGN_POLL_S = 300     # LIVE propagation trickles past finished:true (t+200 s seen)
CYCLES = 3             # unpublish→publish→verify attempts per target


def live_present(ld, path):
    """True iff the node exists in LIVE (transient read fault counts as present
    so a flaky read never causes a wrong skip — the sequence is idempotent)."""
    return ld._live_child_count(path) is not None


def area_alignment(ld, area_path):
    """(aligned, edit_count, live_count) of an area's direct children by
    (name, uuid), EDIT vs LIVE. An area with no EDIT children (or absent in
    EDIT) has nothing to align — reported aligned with count 0.
    LIVE reads right after a publish can hit the async publication job
    mid-settle (ItemNotFoundException on a child uuid, observed live
    2026-07-20 — it killed the whole run with 40+ pages left): retry briefly,
    then report misaligned so the caller republish path takes over. A
    transient fault must never crash the sequence."""
    edit = ld._area_children(area_path, "EDIT")
    if not edit:
        return True, 0, 0
    for attempt in range(3):
        try:
            live = ld._area_children(area_path, "LIVE") or {}
            return live == edit, len(edit), len(live)
        except Exception as e:
            print(f"    ! LIVE read {area_path} (attempt {attempt + 1}/3): "
                  f"{str(e)[:120]}", file=sys.stderr)
            time.sleep(2)
    return False, len(edit), 0


_PURGE_UNPROVEN_STREAK = [0]   # consecutive pages whose purge never signalled


def unpublish_publish_verify(ld, target, verify_area, label):
    """The proven unpublish-first sequence on one target, verified by (name,
    uuid) alignment of verify_area (None → publish blindly; the final belt is
    then the only verification). Raises RuntimeError after CYCLES failures —
    the caller records the failure and continues with the other targets.
    ADAPTIVE PURGE POLL (2026-07-21): after a full-site rebuild every page is
    stale and this environment delivers no purge signal — 111 pages each
    burning the full PURGE_POLL_S turned one publish into hours (observed
    live). Three consecutive unproven purges drop the wait to 5s for the
    rest of the run; the (name,uuid) ALIGNMENT poll below stays the real
    correctness gate, unchanged."""
    edit = ld._area_children(verify_area, "EDIT") or {} if verify_area else None
    for attempt in range(CYCLES):
        # 1. unpublish: instant LIVE purge + publication-metadata reset
        try:
            ld.m.unpublish(target)
        except Exception as e:
            print(f"    ! unpublish {target} (attempt {attempt + 1}): "
                  f"{str(e)[:140]}", file=sys.stderr)
        purge_wait = 5 if _PURGE_UNPROVEN_STREAK[0] >= 3 else PURGE_POLL_S
        deadline = time.time() + purge_wait
        live_n = ld._live_child_count(target)
        while live_n not in (0, None) and time.time() < deadline:
            time.sleep(2)
            live_n = ld._live_child_count(target)
        if live_n not in (0, None):
            # purge unproven — still publish (alignment below is the real gate)
            _PURGE_UNPROVEN_STREAK[0] += 1
            print(f"    ! {label}: LIVE not proven purged by unpublish "
                  f"(attempt {attempt + 1}/{CYCLES}, waited {purge_wait}s) — "
                  f"publishing anyway", file=sys.stderr)
        else:
            _PURGE_UNPROVEN_STREAK[0] = 0
        # 2. publish: actually runs now that the metadata was reset
        try:
            ld.m.publish(target)
        except Exception as e:
            print(f"    ! publish {target} (attempt {attempt + 1}): "
                  f"{str(e)[:140]}", file=sys.stderr)
        if edit is None:
            return  # nothing to align — the final belt verifies
        # 3. poll until FULL (name,uuid) equality — propagation trickles
        deadline = time.time() + ALIGN_POLL_S
        while time.time() < deadline:
            try:
                live = ld._area_children(verify_area, "LIVE") or {}
            except Exception:
                live = None  # transient read fault — keep polling
            if live == edit:
                return
            time.sleep(3)
        print(f"    ! {label}: LIVE still misaligned after attempt "
              f"{attempt + 1}/{CYCLES} — restarting unpublish+publish",
              file=sys.stderr)
    raise RuntimeError(
        f"publish_site: {label} FAILED — LIVE children still misaligned with "
        f"EDIT (name,uuid) after {CYCLES} unpublish+publish attempts (NB: the "
        f"target may be left unpublished in LIVE). The final belt will be red; "
        f"re-run publish_site.sh once the cause is fixed (it is idempotent).")


def main():
    ap = argparse.ArgumentParser(
        description="Single final publication act (EDIT-only doctrine).")
    ap.add_argument("project")
    ap.add_argument("site")
    ap.add_argument("--locale", default="en")
    ap.add_argument("--dry", action="store_true",
                    help="list what would be published/skipped, zero writes")
    a = ap.parse_args()
    ld = Loader(a.project, a.site, locale=a.locale)
    pages = list(ld.content.get("pages", {}).keys())
    if not pages:
        sys.exit(f"publish_site: no pages in the content-load plan for {a.project}")
    # chrome areas from the plan's area-flagged instances (plan-derived)
    chrome = sorted({i["area"] for p in ld.content["pages"].values()
                     for i in p.get("instances", []) if i.get("area")})
    published, aligned_skips, failed = 0, 0, []

    # ── 1. DAM files first (weakref targets must resolve in LIVE) ─────────
    files_path = f"/sites/{a.site}/files"
    print("== files ==")
    if a.dry:
        print(f"  ~ {files_path}: would publish (plain — DAM uuids never diverge)")
    else:
        try:
            ld.m.publish(files_path)
            published += 1
            print(f"  + {files_path}: published (belt verifies LIVE media count)")
        except Exception as e:
            failed.append(("files", str(e)[:140]))
            print(f"  ! {files_path}: publish failed: {str(e)[:140]}", file=sys.stderr)

    # ── 2. chrome areas ────────────────────────────────────────────────────
    if chrome:
        print("== chrome ==")
    for area in chrome:
        apath = f"/sites/{a.site}/home/{area}"
        ok, n_edit, n_live = area_alignment(ld, apath)
        if ok and live_present(ld, apath):
            aligned_skips += 1
            print(f"  = {area}: already aligned ({n_edit} node(s)) — skipped")
            continue
        if a.dry:
            print(f"  ~ {area}: would unpublish+publish (EDIT {n_edit} / LIVE {n_live})")
            continue
        try:
            unpublish_publish_verify(ld, apath, apath, f"chrome {area}")
            published += 1
            print(f"  + {area}: published+verified ({n_edit} node(s) aligned)")
        except RuntimeError as e:
            failed.append((f"chrome {area}", str(e)[:180]))
            print(f"  ! {area}: {e}", file=sys.stderr)

    # ── 3. pages ───────────────────────────────────────────────────────────
    print("== pages ==")
    for slug in pages:
        page_base = ld._slug_to_jcr_path(slug)
        main_area = f"{page_base}/main"
        if slug == "home":
            # GUARD: never unpublish the /home node subtree (= the whole site).
            # The home page node is created published with the site; only its
            # main area (and shell) need the sequence.
            target, verify = main_area, main_area
        else:
            target, verify = page_base, main_area
        ok, n_edit, n_live = area_alignment(ld, main_area)
        if ok and live_present(ld, target):
            aligned_skips += 1
            print(f"  = {slug}: already aligned ({n_edit} node(s)) — skipped")
            continue
        if a.dry:
            print(f"  ~ {slug}: would unpublish+publish {target} "
                  f"(main EDIT {n_edit} / LIVE {n_live})")
            continue
        try:
            unpublish_publish_verify(ld, target, verify, f"page {slug}")
            if slug == "home" and (ld.content["pages"][slug] or {}).get("shell"):
                # home's shell sits outside its main area — publish it too
                try:
                    ld.m.publish(f"{page_base}/shell")
                except Exception:
                    pass  # belt-level: shell absence shows in ground truth
            published += 1
            print(f"  + {slug}: published+verified ({n_edit}/{n_edit} aligned)")
        except RuntimeError as e:
            failed.append((f"page {slug}", str(e)[:180]))
            print(f"  ! {slug}: {e}", file=sys.stderr)

    print(f"\npublish_site: {published} published / {aligned_skips} already-aligned"
          f" / {len(failed)} failed{' [dry]' if a.dry else ''}")
    for label, err in failed:
        print(f"  - FAILED {label}: {err}")
    if a.dry:
        return 0
    # ── final strict belt: the publication is only done when it proves out ──
    print("\n== integrity belt (step_publish_final) ==")
    rc = subprocess.call([sys.executable, "orchestration/probes/integrity.py",
                          f"projects/{a.project}", a.site,
                          "--phase", "step_publish_final"])
    return rc or (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
