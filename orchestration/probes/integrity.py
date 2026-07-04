#!/usr/bin/env python3
"""integrity.py — the ENGINE-LEVEL INTEGRITY BELT (plan-independent completeness).

Per-step probes are GATES: they assert what a single step promised. This belt is
DIFFERENT — it reads the SOURCE OF TRUTH (Jahia, via read-only GraphQL) and diffs
it against EXPECTATIONS derived MECHANICALLY from the pipeline artifacts, with no
hand-declared numbers. It exists because a weak step probe can pass while the
reality is empty (observed live: `content.get` on /home alone passed with 0/19
sub-pages created). The engine runs this as an ADDITIONAL verification after a
content step's own probes pass, so a green step probe can never hide a hollow site.

EXPECTATIONS (mechanical, artifact-derived — never hardcoded):
  * pages   : <PP>/workflow-output/page-inventory.json → the flat page tree the
              loader creates under /sites/<site>/home (create_pages.py slugs, minus
              a "home" slug which maps to /home itself).
  * insts   : orchestration/content/<project>.content-load.json → per page, the
              instances the loader ATTEMPTS in the page's main area: non-area-flagged
              top-level instances (parent is None) + their child items. This is an
              UPPER BOUND (the loader additionally skips unmapped/undeployed/empty
              leaves at runtime), so the belt fails HARD only on the decisive signal
              — a page that expects content but has ZERO instances (the 0/19 case) —
              and REPORTS proportional drift below `--min-ratio` as a mismatch.
  * media   : orchestration/images/<project>.dam.json (if present) → count of unique
              DAM uploads; diffed against jnt:file descendants of /sites/<site>/files.

REALITY (read-only GraphQL against $JAHIA_URL from .env.local):
  * page tree : jnt:page children of /sites/<site>/home (names + count), EDIT + LIVE.
  * instances : content children of each page's /main area (recursive count).
  * media     : jnt:file descendants under /sites/<site>/files.

PHASE-AWARENESS (--phase <step_id>): expectations scale with pipeline position.
  step_pages          → page tree only (EDIT).
  step_content_load   → page tree + per-page instances (EDIT).
  step_publish_parity → page tree + instances + media, checked in LIVE too (parity).
  (default / unknown) → check everything derivable, EDIT + LIVE where sensible.

Output: <PP>/workflow-output/integrity-report.json + a human summary listing every
mismatch. Exit 1 on any mismatch, 0 clean. Read-only, idempotent, <60s.

Usage:
  integrity.py <projects/name> <site> [--phase <step_id>] [--min-ratio 0.5] [--json]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# phase → which checks to run. Encoded as a small table so pipeline position, not
# the caller, decides the expectation surface. LIVE parity is only expected once
# publication is the promised outcome (step_publish_parity).
PHASE_CHECKS: dict[str, dict[str, bool]] = {
    "step_pages": {"pages": True, "instances": False, "media": False, "live": False},
    "step_content_load": {"pages": True, "instances": True, "media": True, "live": False},
    "step_publish_parity": {"pages": True, "instances": True, "media": True, "live": True},
}
# default when --phase is absent or unknown: check everything derivable, both WS.
DEFAULT_CHECKS = {"pages": True, "instances": True, "media": True, "live": True}


# ── environment (read-only; same .env.local contract as mcp_client / _lib.sh) ──
def load_env() -> tuple[str, str, str]:
    """Return (jahia_url, user, password) from the repo-root .env.local
    (ORCHESTRATOR_ENV_FILE overridable). Origin MUST equal JAHIA_URL (rule 6)."""
    path = os.environ.get("ORCHESTRATOR_ENV_FILE") or os.path.join(REPO_ROOT, ".env.local")
    url = os.environ.get("JAHIA_URL", "")
    user = os.environ.get("JAHIA_USER", "")
    pw = os.environ.get("JAHIA_PASS", "")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k in ("JAHIA_URL", "JAHIA_HOST"):
                    url = url or v
                elif k == "JAHIA_USER":
                    user = user or v
                elif k == "JAHIA_PASS":
                    pw = pw or v
    except OSError:
        pass
    return url.rstrip("/"), user or "root", pw or "root"


class Jahia:
    """Minimal read-only GraphQL client (never writes; Origin==JAHIA_URL)."""

    def __init__(self, url: str, user: str, pw: str):
        self.url = url
        auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
        self.headers = {
            "Content-Type": "application/json",
            "Origin": url,
            "Authorization": "Basic " + auth,
        }

    def gql(self, query: str, timeout: float = 30.0) -> dict:
        body = json.dumps({"query": query}).encode()
        req = urllib.request.Request(self.url + "/modules/graphql", body, self.headers)
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode()
        out = json.loads(raw)
        if out.get("errors"):
            raise RuntimeError(f"GraphQL error: {out['errors'][:2]}")
        return out.get("data") or {}

    def page_children(self, site: str, workspace: str) -> list[str]:
        """jnt:page children of /sites/<site>/home (the flat page tree)."""
        q = ('{ jcr(workspace: %s) { nodeByPath(path: "/sites/%s/home") { '
             'children(typesFilter: {types: ["jnt:page"]}) { nodes { name } } } } }'
             % (workspace, site))
        d = self.gql(q)
        node = (d.get("jcr") or {}).get("nodeByPath")
        if not node:
            return []
        return [n["name"] for n in node["children"]["nodes"]]

    def main_area_count(self, site: str, page_name: str, workspace: str) -> int | None:
        """Recursive count of content descendants under a page's /main area.
        Returns None when the /main area node does not exist yet (Jahia lazy-
        creates it) — distinct from 0 (area exists, empty)."""
        path = f"/sites/{site}/home/{page_name}/main"
        q = ('{ jcr(workspace: %s) { nodeByPath(path: "%s") { '
             'descendants { nodes { name } } } } }' % (workspace, path))
        try:
            d = self.gql(q)
        except RuntimeError:
            return None  # path does not exist → not-yet-created area
        node = (d.get("jcr") or {}).get("nodeByPath")
        if not node:
            return None
        return len(node["descendants"]["nodes"])

    def dam_file_count(self, site: str, workspace: str) -> int:
        """jnt:file descendants under /sites/<site>/files."""
        q = ('{ jcr(workspace: %s) { nodeByPath(path: "/sites/%s/files") { '
             'descendants(typesFilter: {types: ["jnt:file"]}) { nodes { name } } } } }'
             % (workspace, site))
        try:
            d = self.gql(q)
        except RuntimeError:
            return 0
        node = (d.get("jcr") or {}).get("nodeByPath")
        if not node:
            return 0
        return len(node["descendants"]["nodes"])


# ── expectations (mechanical, artifact-derived) ──────────────────────────────
def load_json(path: str, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def expected_pages(pp: str) -> list[str]:
    """Page NODE NAMES the loader creates under /home, from page-inventory.json.
    create_pages.py names each page after its slug (flat), EXCEPT a slug of
    "home" which maps to /home itself (no distinct child node)."""
    inv = load_json(os.path.join(REPO_ROOT, pp, "workflow-output", "page-inventory.json"), {})
    names = []
    for p in inv.get("pages", []):
        slug = p.get("slug")
        if not slug or slug == "home":
            continue
        names.append(slug)
    return names


def expected_instances(project: str) -> dict[str, int]:
    """Per page slug → the instance count the loader ATTEMPTS in the page's main
    area: non-area-flagged top-level instances (parent is None) plus their child
    items. Mirrors load_content.load_page's iteration surface; an UPPER BOUND
    (the loader further skips unmapped/undeployed/empty leaves at create time)."""
    cl = load_json(os.path.join(REPO_ROOT, "orchestration", "content",
                                f"{project}.content-load.json"), {})
    out: dict[str, int] = {}
    for slug, pdata in (cl.get("pages") or {}).items():
        insts = pdata.get("instances") or []
        top = [i for i in insts if not i.get("area") and i.get("parent") is None]
        child_items = sum(len(i.get("children") or []) for i in insts if not i.get("area"))
        out[slug] = len(top) + child_items
    return out


def expected_media(project: str) -> int | None:
    """Count of unique DAM uploads from images/<project>.dam.json (skip null/
    failed entries). Returns None when the artifact is absent (no media phase)."""
    dam = load_json(os.path.join(REPO_ROOT, "orchestration", "images",
                                 f"{project}.dam.json"), None)
    if dam is None:
        return None
    return sum(1 for v in dam.values() if v)


# ── the belt ──────────────────────────────────────────────────────────────
def run(pp: str, site: str, phase: str | None, min_ratio: float) -> dict:
    project = os.path.basename(pp.rstrip("/"))
    checks = PHASE_CHECKS.get(phase or "", DEFAULT_CHECKS)
    url, user, pw = load_env()
    report: dict = {
        "project": project, "projectPath": pp, "site": site,
        "phase": phase or "(default)", "checks": checks,
        "jahiaUrl": url, "ranAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mismatches": [], "sections": {},
    }
    if not url:
        report["mismatches"].append({"kind": "config", "detail": "no JAHIA_URL in env/.env.local"})
        return report
    j = Jahia(url, user, pw)

    # ── pages (EDIT; LIVE too when the phase expects publication) ──────────
    if checks["pages"]:
        exp = expected_pages(pp)
        exp_set = set(exp)
        try:
            actual_edit = j.page_children(site, "EDIT")
        except (urllib.error.URLError, RuntimeError, OSError) as e:
            report["mismatches"].append({"kind": "pages", "detail": f"GraphQL EDIT failed: {e}"})
            actual_edit = []
        act_set = set(actual_edit)
        missing = sorted(exp_set - act_set)
        extra = sorted(act_set - exp_set)
        sec = {"expectedCount": len(exp), "actualCount": len(actual_edit),
               "missing": missing, "extra": extra, "workspace": "EDIT"}
        report["sections"]["pages"] = sec
        for name in missing:
            report["mismatches"].append({"kind": "page_missing", "workspace": "EDIT", "page": name})
        if checks["live"]:
            try:
                actual_live = j.page_children(site, "LIVE")
                live_missing = sorted(exp_set - set(actual_live))
                sec["liveActualCount"] = len(actual_live)
                sec["liveMissing"] = live_missing
                for name in live_missing:
                    report["mismatches"].append({"kind": "page_missing", "workspace": "LIVE", "page": name})
            except (urllib.error.URLError, RuntimeError, OSError) as e:
                report["mismatches"].append({"kind": "pages", "detail": f"GraphQL LIVE failed: {e}"})

    # ── per-page instances (main area) ────────────────────────────────────
    if checks["instances"]:
        exp_inst = expected_instances(project)
        workspaces = ["EDIT"] + (["LIVE"] if checks["live"] else [])
        pages_sec = {}
        for ws in workspaces:
            for slug, exp_n in sorted(exp_inst.items()):
                # a page with NO expected content is not a mismatch if empty
                if exp_n == 0:
                    continue
                # "home" slug → the site home node itself (/home/main); every other
                # slug is a flat child page (/home/<slug>/main), per create_pages.py
                actual = j.main_area_count(site, "home" if slug == "home" else slug, ws)
                got = actual or 0
                entry = pages_sec.setdefault(slug, {"expected": exp_n})
                entry[f"actual_{ws}"] = None if actual is None else actual
                if got == 0:
                    # the decisive, hard signal: content expected, ZERO present
                    report["mismatches"].append({
                        "kind": "instances_empty", "workspace": ws, "page": slug,
                        "expected": exp_n, "actual": 0,
                        "detail": "expected content but main area is empty/absent"})
                elif got < exp_n * min_ratio:
                    report["mismatches"].append({
                        "kind": "instances_drift", "workspace": ws, "page": slug,
                        "expected": exp_n, "actual": got, "minRatio": min_ratio,
                        "detail": f"actual {got} < {min_ratio:.0%} of expected {exp_n}"})
        report["sections"]["instances"] = {"minRatio": min_ratio, "pages": pages_sec}

    # ── media (DAM) ───────────────────────────────────────────────────────
    if checks["media"]:
        exp_m = expected_media(project)
        if exp_m is not None:
            ws = "LIVE" if checks["live"] else "EDIT"
            actual_m = j.dam_file_count(site, ws)
            sec = {"expected": exp_m, "actual": actual_m, "workspace": ws, "minRatio": min_ratio}
            report["sections"]["media"] = sec
            if exp_m > 0 and actual_m < exp_m * min_ratio:
                report["mismatches"].append({
                    "kind": "media_drift", "workspace": ws,
                    "expected": exp_m, "actual": actual_m, "minRatio": min_ratio,
                    "detail": f"DAM files {actual_m} < {min_ratio:.0%} of expected {exp_m}"})

    return report


def human_summary(report: dict) -> str:
    lines = []
    lines.append(f"integrity belt — {report['project']} @ site '{report['site']}' "
                 f"(phase: {report['phase']})")
    secs = report.get("sections", {})
    if "pages" in secs:
        p = secs["pages"]
        extra = f", {len(p['extra'])} extra" if p.get("extra") else ""
        lines.append(f"  pages   : expected {p['expectedCount']}, EDIT {p['actualCount']}"
                     + (f", LIVE {p['liveActualCount']}" if "liveActualCount" in p else "")
                     + f" ({len(p['missing'])} missing{extra})")
    if "instances" in secs:
        pg = secs["instances"]["pages"]
        empties = sum(1 for v in pg.values() if any(
            (v.get(k) or 0) == 0 for k in v if k.startswith("actual_")))
        lines.append(f"  insts   : {len(pg)} page(s) with expected content, "
                     f"{empties} empty (min-ratio {secs['instances']['minRatio']:.0%})")
    if "media" in secs:
        m = secs["media"]
        lines.append(f"  media   : expected {m['expected']}, {m['workspace']} {m['actual']}")
    ms = report.get("mismatches", [])
    if not ms:
        lines.append("  RESULT  : CLEAN — reality matches artifact-derived expectations.")
    else:
        lines.append(f"  RESULT  : {len(ms)} MISMATCH(es):")
        for m in ms[:40]:
            k = m.get("kind")
            if k == "page_missing":
                lines.append(f"    - MISSING page [{m['workspace']}]: {m['page']}")
            elif k == "instances_empty":
                lines.append(f"    - EMPTY [{m['workspace']}]: {m['page']} "
                             f"(expected {m['expected']}, got 0)")
            elif k == "instances_drift":
                lines.append(f"    - DRIFT [{m['workspace']}]: {m['page']} "
                             f"expected {m['expected']}, got {m['actual']}")
            elif k == "media_drift":
                lines.append(f"    - MEDIA DRIFT [{m['workspace']}]: "
                             f"expected {m['expected']}, got {m['actual']}")
            else:
                lines.append(f"    - {k}: {m.get('detail', '')}")
        if len(ms) > 40:
            lines.append(f"    … and {len(ms) - 40} more")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Engine-level integrity belt (read-only).")
    ap.add_argument("project_path", help="projects/<name>")
    ap.add_argument("site", help="Jahia site key")
    ap.add_argument("--phase", help="pipeline step id — scales expectations")
    ap.add_argument("--min-ratio", type=float, default=0.5,
                    help="fail a page/media if actual < ratio*expected (default 0.5)")
    ap.add_argument("--json", action="store_true", help="print the report JSON to stdout")
    a = ap.parse_args()

    pp = a.project_path.rstrip("/")
    report = run(pp, a.site, a.phase, a.min_ratio)

    out_dir = os.path.join(REPO_ROOT, pp, "workflow-output")
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "integrity-report.json"), "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"integrity: could not write report: {e}", file=sys.stderr)

    if a.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(human_summary(report))
    return 1 if report.get("mismatches") else 0


if __name__ == "__main__":
    sys.exit(main())
