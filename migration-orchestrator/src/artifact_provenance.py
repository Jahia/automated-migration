"""artifact_provenance.py — per-project artifact freshness (P3b observability).

P0 (provenance.py / provenance.mjs) stamps every pipeline artifact with
`{run_id, step_id, generated_at, git_sha, tool, args, page_set}`: JSON dict
artifacts embed it under a top-level "_provenance" key, and artifact
DIRECTORIES (mirror/, reconstruct/, groundtruth/, segment/, compose/,
zone-overlay/) get a `<dir>/provenance.json` sidecar for the last invocation
that touched them (see provenance.py's docstring for the placement contract).

This module answers the next question: given those stamps, is an artifact
STALE — i.e. did something upstream in the pipeline regenerate AFTER this
artifact was produced, so it may no longer reflect the current inputs?

STAGE DAG — SINGLE SOURCE, mirrored from `orchestration/assist/invalidate.sh`
(its `downstream_stages()` table is the canonical DAG; `stage_paths()` is the
canonical per-stage artifact list). Keep the two in sync by hand — invalidate.sh
is a bash script and cannot import this module. STAGE_PREDECESSORS below is
the direct-predecessor form of exactly that same graph:

    crawl -> mirror -> semantic -> {segment | zone} -> model -> contentload
           -> compose -> cnd -> reconstruct -> {load | dam} -> groundtruth

`segment`/`zone` are ALTERNATE arms at the same DAG position (neither is
upstream of the other); same for `load`/`dam`.

STALE rule (deterministic): an artifact A in stage S is stale when some stage
strictly upstream of S (transitively) has a newer effective timestamp than A's
own. "Effective timestamp" = the artifact's `_provenance.generated_at` when
present, else the file's (or directory's newest child's) mtime — so a pre-P0
artifact with no stamp still participates in staleness detection, it just
reports run_id/git_sha as null (never crashes on old artifacts).

Read-only, pure filesystem reads. Never raises: any per-artifact failure
degrades to an absent/unknown entry rather than sinking the whole report.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .migration_control import read_json_provenance

log = logging.getLogger(__name__)


# ── the DAG (direct predecessors) — mirrors invalidate.sh's downstream_stages() ──
STAGE_PREDECESSORS: dict[str, list[str]] = {
    "crawl": [],
    "mirror": ["crawl"],
    "semantic": ["mirror"],
    "segment": ["semantic"],
    "zone": ["semantic"],
    "model": ["segment", "zone"],
    "contentload": ["model"],
    "compose": ["contentload"],
    "cnd": ["compose"],
    "reconstruct": ["cnd"],
    "load": ["reconstruct"],
    "dam": ["reconstruct"],
    "groundtruth": ["load", "dam"],
}


@dataclass(frozen=True)
class ArtifactSpec:
    artifact: str    # stable short id — the FE's lookup key
    stage: str       # DAG stage this artifact belongs to (see STAGE_PREDECESSORS)
    kind: str        # "file" | "dir" | "groundtruth" (dual full/partial report)
    rel_path: str    # relative to `base`; "{project}" is substituted
    base: str = "wo"  # "wo" = <project>/workflow-output/, "repo" = harness root


# ── the artifact registry — mirrors invalidate.sh's stage_paths() tables ──
# One representative artifact per stage, plus the extra entries the cockpit
# panels already reference by name (both mirror outputs, both zone outputs) —
# see MirrorGate.tsx / ComponentModelView.tsx. Kept to the artifacts that
# actually carry (or could carry) a provenance stamp; e.g. `zone-review.html`,
# `definitions.cnd` or the model stage's other JSON siblings (orphans.json,
# grouping.json, ...) are not independently tracked here.
ARTIFACT_SPECS: list[ArtifactSpec] = [
    ArtifactSpec("page-inventory", "crawl", "file", "page-inventory.json"),
    ArtifactSpec("local-mirror", "mirror", "file", "local-mirror/mirror.json"),
    ArtifactSpec("mirror-check", "mirror", "dir", "mirror"),
    ArtifactSpec("semantic-candidates", "semantic", "file", "semantic-candidates.json"),
    ArtifactSpec("semantic-templates", "semantic", "file", "semantic-templates.json"),
    ArtifactSpec("segment", "segment", "dir", "segment"),
    ArtifactSpec("zone", "zone", "file", "zone3-{project}.json"),
    ArtifactSpec("zone-overlay", "zone", "dir", "zone-overlay"),
    ArtifactSpec("component-manifest", "model", "file", "component-manifest.json"),
    ArtifactSpec("contentload", "contentload", "file",
                 "orchestration/content/{project}.content-load.json", base="repo"),
    ArtifactSpec("compose", "compose", "dir", "compose"),
    ArtifactSpec("cnd", "cnd", "file", "views.json"),
    ArtifactSpec("reconstruct", "reconstruct", "dir", "reconstruct"),
    ArtifactSpec("load-ledger", "load", "file", "load-ledger.json"),
    ArtifactSpec("dam", "dam", "file", "orchestration/images/{project}.dam.json", base="repo"),
    # dual-file (P3a): groundtruth.json (full) vs groundtruth.partial.json (--pages
    # subset) — see groundtruth_probe.mjs. Handled as ONE artifact entry that
    # reports whichever of the two is freshest.
    ArtifactSpec("groundtruth", "groundtruth", "groundtruth", "groundtruth"),
]


def _upstream_stages(stage: str) -> set[str]:
    """Transitive closure of STAGE_PREDECESSORS — every stage strictly upstream
    of `stage` in the DAG (the set a newer artifact would make `stage` stale)."""
    seen: set[str] = set()
    stack = list(STAGE_PREDECESSORS.get(stage, []))
    while stack:
        s = stack.pop()
        if s in seen:
            continue
        seen.add(s)
        stack.extend(STAGE_PREDECESSORS.get(s, []))
    return seen


def _parse_ts(generated_at: object) -> float | None:
    """ISO-8601 UTC (either provenance.py's no-millis or provenance.mjs's
    toISOString-with-millis form) -> epoch seconds. None on anything else —
    never raises."""
    if not isinstance(generated_at, str) or not generated_at:
        return None
    try:
        return datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_dir_sidecar(dir_path: Path) -> dict | None:
    """<dir>/provenance.json — its content IS the provenance record (no
    "_provenance" wrapper, unlike a stamped JSON artifact); see provenance.py's
    write_sidecar. None when absent/corrupt."""
    p = dir_path / "provenance.json"
    try:
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        pass
    return None


def _file_signal(path: Path) -> tuple[bool, dict | None, float | None]:
    """(exists, provenance-or-None, effective_ts) for a single JSON file:
    generated_at from its stamp (in-file or sidecar) when present, else the
    file's own mtime — a pre-P0 file still yields a usable timestamp."""
    if not path.is_file():
        return False, None, None
    prov = read_json_provenance(path)
    ts = _parse_ts(prov.get("generated_at")) if prov else None
    if ts is None:
        try:
            ts = path.stat().st_mtime
        except OSError:
            ts = None
    return True, prov, ts


def _dir_signal(path: Path) -> tuple[bool, dict | None, float | None]:
    """Same shape as `_file_signal` for a directory artifact (mirror/,
    reconstruct/, segment/, compose/, zone-overlay/): provenance from the
    `provenance.json` sidecar, else the newest direct child's mtime."""
    if not path.is_dir():
        return False, None, None
    prov = _read_dir_sidecar(path)
    ts = _parse_ts(prov.get("generated_at")) if prov else None
    if ts is None:
        try:
            children = [c.stat().st_mtime for c in path.iterdir() if c.is_file()]
            ts = max(children) if children else path.stat().st_mtime
        except OSError:
            ts = None
    return True, prov, ts


def _groundtruth_signal(wo: Path) -> tuple[bool, dict | None, float | None, dict | None]:
    """groundtruth.json (full) vs groundtruth.partial.json (--pages subset):
    report whichever is FRESHER (ties favor the full report). `partial` is
    populated ONLY when the partial variant wins — a full report that is the
    freshest is not flagged partial even though it also carries pages_covered/
    pages_total (they equal pages_total on a full run)."""
    gdir = wo / "groundtruth"
    full_exists, full_prov, full_ts = _file_signal(gdir / "groundtruth.json")
    part_exists, part_prov, part_ts = _file_signal(gdir / "groundtruth.partial.json")
    if not full_exists and not part_exists:
        return False, None, None, None
    use_partial = part_exists and (not full_exists or (part_ts or 0) > (full_ts or 0))
    if use_partial:
        prov, ts, path = part_prov, part_ts, gdir / "groundtruth.partial.json"
    else:
        prov, ts, path = full_prov, full_ts, gdir / "groundtruth.json"
    partial_info = None
    if use_partial:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            partial_info = {"pages_covered": raw.get("pages_covered"), "pages_total": raw.get("pages_total")}
        except (OSError, ValueError):
            partial_info = None
    return True, prov, ts, partial_info


def _resolve_path(spec: ArtifactSpec, wo: Path, repo_root: Path, project: str) -> Path:
    """`spec`'s absolute path. Traversal-guarded belt-and-suspenders style (like
    invalidate.sh's remove_path allow-list): a "wo" artifact must resolve inside
    this project's workflow-output; a "repo" artifact (contentload/dam — the two
    DAG stages that write outside workflow-output by design) must be EXACTLY one
    of the two externally-anchored files invalidate.sh names. `project` reaching
    here is already `_valid_project`-checked by the route (bare segment, no `/`
    or `..`) so this can't actually be escaped — the check is defence in depth."""
    rel = spec.rel_path.format(project=project)
    if spec.base == "wo":
        base = wo.resolve()
        target = (base / rel).resolve()
        if target != base and not str(target).startswith(str(base) + "/"):
            raise ValueError(f"artifact path escaped workflow-output: {spec.artifact}")
        return target
    target = (repo_root / rel).resolve()
    allowed = {
        (repo_root / "orchestration" / "content" / f"{project}.content-load.json").resolve(),
        (repo_root / "orchestration" / "images" / f"{project}.dam.json").resolve(),
    }
    if target not in allowed:
        raise ValueError(f"artifact path not allow-listed: {spec.artifact}")
    return target


def _signal(spec: ArtifactSpec, wo: Path, repo_root: Path, project: str) -> dict:
    """One spec -> its raw signal dict (still carries the internal _effective_ts
    used only for the cross-stage staleness comparison, stripped before the
    response is returned)."""
    try:
        if spec.kind == "groundtruth":
            exists, prov, ts, partial = _groundtruth_signal(wo)
        else:
            path = _resolve_path(spec, wo, repo_root, project)
            fn = _file_signal if spec.kind == "file" else _dir_signal
            exists, prov, ts = fn(path)
            partial = None
    except Exception as e:  # never let one bad spec sink the whole report
        log.warning(f"artifact_provenance: {spec.artifact} unavailable: {e}")
        exists, prov, ts, partial = False, None, None, None
    return {
        "artifact": spec.artifact,
        "stage": spec.stage,
        "path": spec.rel_path.format(project=project),
        "exists": exists,
        "generated_at": (prov or {}).get("generated_at"),
        "run_id": (prov or {}).get("run_id"),
        "git_sha": (prov or {}).get("git_sha"),
        "partial": partial,
        "_effective_ts": ts,
    }


def project_artifact_report(project_dir: Path, repo_root: Path, project: str) -> list[dict]:
    """Provenance + staleness summary for every known artifact of one project,
    in DAG order. `project_dir` = <repo_root>/projects/<project> (may or may not
    exist — a fresh/zero-run project reports every artifact as exists:false).
    Each entry: {artifact, stage, path, exists, generated_at, run_id, git_sha,
    partial, stale, stale_reason}."""
    wo = project_dir / "workflow-output"
    entries = {spec.artifact: _signal(spec, wo, repo_root, project) for spec in ARTIFACT_SPECS}

    # stage effective time = the MAX timestamp over that stage's own EXISTING
    # artifacts (a stage with nothing on disk yet contributes no signal — it
    # cannot make anything downstream "stale" relative to work that never ran).
    stage_ts: dict[str, float] = {}
    for e in entries.values():
        if e["exists"] and e["_effective_ts"] is not None:
            stage_ts[e["stage"]] = max(stage_ts.get(e["stage"], e["_effective_ts"]), e["_effective_ts"])

    out: list[dict] = []
    for spec in ARTIFACT_SPECS:
        e = entries[spec.artifact]
        stale, reason = False, None
        if e["exists"] and e["_effective_ts"] is not None:
            newer = sorted(
                ((s, stage_ts[s]) for s in _upstream_stages(spec.stage)
                 if s in stage_ts and stage_ts[s] > e["_effective_ts"]),
                key=lambda p: p[1], reverse=True,
            )
            if newer:
                stale = True
                reason = "upstream regenerated after this artifact: " + ", ".join(
                    f"{s} ({_iso(ts)})" for s, ts in newer)
        e.pop("_effective_ts")
        e["stale"] = stale
        e["stale_reason"] = reason
        out.append(e)
    return out
