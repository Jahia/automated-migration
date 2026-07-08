"""Artifact provenance / staleness tests (P3b).

artifact_provenance.project_artifact_report reads the P0 _provenance stamps
(embedded "_provenance" key for JSON dict artifacts, or a <dir>/provenance.json
sidecar for directory artifacts — mirror/, reconstruct/, groundtruth/, segment/,
compose/, zone-overlay/) and flags an artifact STALE when some DAG-upstream
stage (orchestration/assist/invalidate.sh's stage graph) has a newer effective
timestamp (generated_at, falling back to mtime for pre-P0 artifacts that carry
no stamp at all). These tests fabricate a throwaway project tree under
tmp_path — nothing touches the live projects/ dir or orchestrator.db.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import artifact_provenance as ap
from src.routes import content_progress as cp
from src.routes import projects as proj_routes

# Fixed epoch base + 1h steps: deterministic, strictly-ordered fixture timestamps
# without fiddling with real calendar dates.
_T0 = 1_799_000_000.0


def _ts(i: int) -> float:
    return _T0 + i * 3600


def _iso(i: int) -> str:
    return ap._iso(_ts(i))


def _prov(i: int, run_id: str = "run_x", git_sha: str = "abc123def456", tool: str = "t") -> dict:
    return {"run_id": run_id, "step_id": None, "generated_at": _iso(i),
            "git_sha": git_sha, "tool": tool, "args": [], "page_set": None}


def _write_json(path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_stamped(path, i: int, extra: dict | None = None, **prov_kwargs):
    data = dict(extra or {})
    data["_provenance"] = _prov(i, **prov_kwargs)
    _write_json(path, data)


def _write_dir_sidecar(dir_path, i: int, **prov_kwargs):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "provenance.json").write_text(json.dumps(_prov(i, **prov_kwargs)))


def _touch(path, i: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    os.utime(path, (_ts(i), _ts(i)))


def _report(tmp_path, project: str = "demo") -> dict[str, dict]:
    project_dir = tmp_path / "projects" / project
    return {e["artifact"]: e for e in ap.project_artifact_report(project_dir, tmp_path, project)}


def _wo(tmp_path, project: str = "demo"):
    return tmp_path / "projects" / project / "workflow-output"


# ── the DAG itself ────────────────────────────────────────────────────────
def test_registry_covers_every_dag_stage():
    stages_in_registry = {spec.stage for spec in ap.ARTIFACT_SPECS}
    assert stages_in_registry == set(ap.STAGE_PREDECESSORS)


def test_upstream_stages_crawl_is_root():
    assert ap._upstream_stages("crawl") == set()


def test_upstream_stages_segment_zone_are_isolated_siblings():
    # alternate arms at the same DAG position — neither is upstream of the other
    assert ap._upstream_stages("segment") == {"crawl", "mirror", "semantic"}
    assert ap._upstream_stages("zone") == {"crawl", "mirror", "semantic"}


def test_upstream_stages_load_dam_are_isolated_siblings():
    up = {"crawl", "mirror", "semantic", "segment", "zone", "model", "contentload", "compose", "cnd", "reconstruct"}
    assert ap._upstream_stages("load") == up
    assert ap._upstream_stages("dam") == up


def test_upstream_stages_groundtruth_is_full_closure():
    assert ap._upstream_stages("groundtruth") == set(ap.STAGE_PREDECESSORS) - {"groundtruth"}


# ── missing project / zero-run: every artifact reports absent, never crashes ──
def test_missing_project_all_absent(tmp_path):
    report = _report(tmp_path)
    assert len(report) == len(ap.ARTIFACT_SPECS)
    for e in report.values():
        assert e["exists"] is False
        assert e["generated_at"] is None
        assert e["run_id"] is None
        assert e["git_sha"] is None
        assert e["partial"] is None
        assert e["stale"] is False
        assert e["stale_reason"] is None


# ── a fully fresh, correctly-ordered chain: nothing is stale ──────────────
def test_fresh_chain_nothing_stale(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "page-inventory.json", 0, {"pages": []})
    _write_stamped(wo / "local-mirror" / "mirror.json", 1, {"pages": []})
    _write_dir_sidecar(wo / "mirror", 1)
    _write_stamped(wo / "semantic-candidates.json", 2, {"components": []})
    _write_stamped(wo / "semantic-templates.json", 2, {})
    _write_stamped(wo / "zone3-demo.json", 3, {})
    _write_dir_sidecar(wo / "zone-overlay", 3)
    _write_stamped(wo / "component-manifest.json", 4, {"components": []})
    _write_dir_sidecar(wo / "compose", 5)
    _write_stamped(wo / "views.json", 6, {})
    _write_dir_sidecar(wo / "reconstruct", 7)
    _write_stamped(wo / "load-ledger.json", 8, {})
    _write_stamped(wo / "groundtruth" / "groundtruth.json", 9,
                   {"pages_covered": 5, "pages_total": 5})

    report = _report(tmp_path)
    for artifact, e in report.items():
        if artifact in ("contentload", "dam", "segment"):
            continue  # not populated in this fixture (untouched arm / external file)
        assert e["exists"] is True, artifact
        assert e["stale"] is False, f"{artifact}: {e['stale_reason']}"
        assert e["stale_reason"] is None


# ── an upstream stage regenerated AFTER a downstream one: flagged stale ───
def test_stale_when_upstream_regenerated_later(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "component-manifest.json", 1, {"components": []})  # model, early
    _write_stamped(wo / "zone3-demo.json", 5, {})                          # zone, LATER (upstream of model)

    report = _report(tmp_path)
    assert report["component-manifest"]["stale"] is True
    assert "zone" in report["component-manifest"]["stale_reason"]
    assert _iso(5) in report["component-manifest"]["stale_reason"]
    # the artifact ahead in the DAG is unaffected by what's downstream of it
    assert report["zone"]["stale"] is False


def test_stale_reason_lists_every_offending_upstream_stage(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "component-manifest.json", 1, {"components": []})
    _write_stamped(wo / "zone3-demo.json", 5, {})
    _write_dir_sidecar(wo / "mirror", 6)
    _write_stamped(wo / "local-mirror" / "mirror.json", 6, {})

    reason = _report(tmp_path)["component-manifest"]["stale_reason"]
    assert "zone" in reason and "mirror" in reason


# ── same-stage siblings never invalidate each other ───────────────────────
def test_same_stage_siblings_do_not_invalidate_each_other(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "local-mirror" / "mirror.json", 2, {})  # newer
    _write_dir_sidecar(wo / "mirror", 1)                        # older, same stage

    report = _report(tmp_path)
    assert report["mirror-check"]["stale"] is False  # sibling being newer doesn't count
    assert report["local-mirror"]["stale"] is False  # nothing upstream of mirror exists


# ── pre-P0 artifact (no _provenance at all): never crashes, mtime fallback ──
def test_pre_p0_artifact_reports_null_provenance_no_crash(tmp_path):
    wo = _wo(tmp_path)
    _write_json(wo / "component-manifest.json", {"components": []})  # no "_provenance" key
    os.utime(wo / "component-manifest.json", (_ts(1), _ts(1)))

    report = _report(tmp_path)
    e = report["component-manifest"]
    assert e["exists"] is True
    assert e["generated_at"] is None
    assert e["run_id"] is None
    assert e["git_sha"] is None


def test_pre_p0_artifact_still_participates_in_staleness_via_mtime(tmp_path):
    wo = _wo(tmp_path)
    (wo).mkdir(parents=True, exist_ok=True)
    (wo / "component-manifest.json").write_text(json.dumps({"components": []}))
    os.utime(wo / "component-manifest.json", (_ts(1), _ts(1)))  # old mtime, no stamp
    _write_stamped(wo / "zone3-demo.json", 5, {})                # upstream, later + stamped

    e = _report(tmp_path)["component-manifest"]
    assert e["generated_at"] is None            # still "provenance inconnue" for display
    assert e["stale"] is True                   # but staleness math used its mtime
    assert "zone" in e["stale_reason"]


def test_pre_p0_upstream_dir_with_no_sidecar_uses_child_mtime(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "component-manifest.json", 1, {"components": []})
    # zone-overlay/ has PNGs but no provenance.json (truly pre-P0 directory)
    _touch(wo / "zone-overlay" / "en.png", 9)

    e = _report(tmp_path)["component-manifest"]
    assert e["stale"] is True
    assert "zone" in e["stale_reason"]


# ── dir-kind artifacts: sidecar is authoritative, else newest child mtime ──
def test_dir_kind_reads_sidecar(tmp_path):
    wo = _wo(tmp_path)
    _write_dir_sidecar(wo / "zone-overlay", 3, run_id="run_ov")
    e = _report(tmp_path)["zone-overlay"]
    assert e["exists"] is True
    assert e["run_id"] == "run_ov"
    assert e["generated_at"] == _iso(3)


def test_dir_kind_without_sidecar_never_crashes(tmp_path):
    wo = _wo(tmp_path)
    _touch(wo / "segment" / "en.page.png", 2)
    _touch(wo / "segment" / "en.segmentation.json", 3)  # not stamped in this fixture
    e = _report(tmp_path)["segment"]
    assert e["exists"] is True
    assert e["generated_at"] is None  # no provenance.json sidecar written


# ── groundtruth: dual-file (full vs --pages partial), freshest wins ───────
def test_groundtruth_full_only(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "groundtruth" / "groundtruth.json", 1,
                   {"pages_covered": 5, "pages_total": 5})
    e = _report(tmp_path)["groundtruth"]
    assert e["exists"] is True
    assert e["partial"] is None
    assert e["generated_at"] == _iso(1)


def test_groundtruth_partial_only(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "groundtruth" / "groundtruth.partial.json", 1,
                   {"pages_covered": 4, "pages_total": 21})
    e = _report(tmp_path)["groundtruth"]
    assert e["exists"] is True
    assert e["partial"] == {"pages_covered": 4, "pages_total": 21}


def test_groundtruth_partial_freshest_flags_partial_and_never_hides_full(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "groundtruth" / "groundtruth.json", 1,
                   {"pages_covered": 21, "pages_total": 21})
    _write_stamped(wo / "groundtruth" / "groundtruth.partial.json", 5,
                   {"pages_covered": 4, "pages_total": 21}, run_id="run_partial")
    e = _report(tmp_path)["groundtruth"]
    assert e["partial"] == {"pages_covered": 4, "pages_total": 21}
    assert e["run_id"] == "run_partial"
    assert e["generated_at"] == _iso(5)
    # both files stay on disk — review.html is never overwritten by a --pages run
    assert (wo / "groundtruth" / "groundtruth.json").is_file()
    assert (wo / "groundtruth" / "groundtruth.partial.json").is_file()


def test_groundtruth_full_freshest_hides_partial_flag(tmp_path):
    wo = _wo(tmp_path)
    _write_stamped(wo / "groundtruth" / "groundtruth.partial.json", 1,
                   {"pages_covered": 4, "pages_total": 21})
    _write_stamped(wo / "groundtruth" / "groundtruth.json", 5,
                   {"pages_covered": 21, "pages_total": 21}, run_id="run_full")
    e = _report(tmp_path)["groundtruth"]
    assert e["partial"] is None  # the freshest report is a full one
    assert e["run_id"] == "run_full"


def test_groundtruth_neither_file_is_absent(tmp_path):
    wo = _wo(tmp_path)
    (wo / "groundtruth").mkdir(parents=True)
    e = _report(tmp_path)["groundtruth"]
    assert e["exists"] is False
    assert e["partial"] is None


# ── contentload / dam live OUTSIDE workflow-output, at the repo root ──────
def test_contentload_and_dam_resolve_under_repo_root(tmp_path):
    _write_stamped(tmp_path / "orchestration" / "content" / "demo.content-load.json", 2,
                   {"pages": {}}, run_id="run_cl")
    _write_stamped(tmp_path / "orchestration" / "images" / "demo.dam.json", 3,
                   {}, run_id="run_dam")
    report = _report(tmp_path)
    assert report["contentload"]["exists"] is True
    assert report["contentload"]["run_id"] == "run_cl"
    assert report["dam"]["exists"] is True
    assert report["dam"]["run_id"] == "run_dam"


def test_resolve_path_rejects_repo_spec_outside_allowlist(tmp_path):
    rogue = ap.ArtifactSpec("rogue", "dam", "file", "../../etc/passwd", base="repo")
    with pytest.raises(ValueError):
        ap._resolve_path(rogue, tmp_path / "projects" / "demo" / "workflow-output", tmp_path, "demo")


def test_resolve_path_rejects_wo_escape(tmp_path):
    rogue = ap.ArtifactSpec("rogue", "crawl", "file", "../../outside.json", base="wo")
    with pytest.raises(ValueError):
        ap._resolve_path(rogue, tmp_path / "projects" / "demo" / "workflow-output", tmp_path, "demo")


def test_signal_degrades_gracefully_on_bad_spec(tmp_path):
    # _signal (unlike _resolve_path) must never raise — one bad spec degrades
    # to an absent entry instead of sinking the whole report.
    rogue = ap.ArtifactSpec("rogue", "crawl", "file", "../../outside.json", base="wo")
    wo = tmp_path / "projects" / "demo" / "workflow-output"
    out = ap._signal(rogue, wo, tmp_path, "demo")
    assert out["exists"] is False
    assert out["_effective_ts"] is None


# ── route: GET /projects/{project}/artifacts ──────────────────────────────
def _client():
    app = FastAPI()
    app.include_router(proj_routes.router)
    return TestClient(app)


def test_route_invalid_project_400(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "_harness_root", lambda: tmp_path)
    resp = _client().get("/projects/..%2F..%2Fetc/artifacts")
    assert resp.status_code in (400, 404)


def test_route_missing_project_404(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "_harness_root", lambda: tmp_path)
    resp = _client().get("/projects/ghost/artifacts")
    assert resp.status_code == 404


def test_route_happy_path_200(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "_harness_root", lambda: tmp_path)
    wo = _wo(tmp_path, "discoverasr")
    _write_stamped(wo / "page-inventory.json", 0, {"pages": []})
    _write_stamped(wo / "component-manifest.json", 1, {"components": []})

    resp = _client().get("/projects/discoverasr/artifacts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project"] == "discoverasr"
    assert len(body["artifacts"]) == len(ap.ARTIFACT_SPECS)
    by_id = {a["artifact"]: a for a in body["artifacts"]}
    assert by_id["page-inventory"]["exists"] is True
    assert by_id["page-inventory"]["generated_at"] == _iso(0)
    assert by_id["reconstruct"]["exists"] is False  # never produced in this fixture


def test_route_zero_run_project_reports_all_absent(tmp_path, monkeypatch):
    # a scaffolded-but-never-run project dir (no workflow-output/ yet at all)
    monkeypatch.setattr(cp, "_harness_root", lambda: tmp_path)
    (tmp_path / "projects" / "fresh").mkdir(parents=True)
    resp = _client().get("/projects/fresh/artifacts")
    assert resp.status_code == 200
    body = resp.json()
    assert all(a["exists"] is False for a in body["artifacts"])
