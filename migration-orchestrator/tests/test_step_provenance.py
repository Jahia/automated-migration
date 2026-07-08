"""Step-provenance / honesty tests (P2 observability).

A partial plan's verify step can go 'done' in ~5ms because its PROBE only
`test -s`'d an artifact an EARLIER run produced — which reads in the UI as "a
full migration ran". migration_control.step_provenance tells the two apart by
reading the _provenance stamp (provenance.py / .mjs) on the step's PRIMARY
workflow-output JSON: a stamp from a DIFFERENT run_id means the step reused the
file rather than doing the work this run. GET /runs/{id}/provenance batches this
per-step for the cockpit. These tests fabricate everything under tmp_path —
nothing touches the live orchestrator.db or projects/.
"""
from __future__ import annotations

import json

import pytest

from src.migration_control import (
    read_json_provenance,
    step_artifact_rel,
    step_provenance,
)
from src.models import EpicState, RunState, StepState, StoryState
from src.routes import runs as runs_routes


# ── step_artifact_rel: derive the primary workflow-output JSON ───────────
def _step(criteria):
    return StepState(id="st", story_id="s1", acceptance_criteria=criteria)


def test_artifact_rel_test_s_probe():
    # a verify step's `test -s <upstream>.json` IS the reuse target
    s = _step(["PROBE: test -s projects/demo/workflow-output/local-mirror/mirror.json"])
    assert step_artifact_rel(s) == "projects/demo/workflow-output/local-mirror/mirror.json"


def test_artifact_rel_out_flag_wins_in_probe():
    s = _step([
        "Run: python3 orchestration/lib/group_llm.py projects/demo --out projects/demo/workflow-output/grouping.json",
        "PROBE: python3 orchestration/lib/assemble_manifest.py x --out projects/demo/workflow-output/component-manifest.json",
    ])
    # PROBE line (the gate/output contract) wins over the Run line's --out
    assert step_artifact_rel(s) == "projects/demo/workflow-output/component-manifest.json"


def test_artifact_rel_out_views_flag():
    s = _step([
        "Run: python3 orchestration/lib/cnd_emit.py m --out-cnd projects/demo/workflow-output/definitions.cnd "
        "--out-views projects/demo/workflow-output/views.json",
        "PROBE: test -s projects/demo/workflow-output/definitions.cnd",
        "PROBE: test -s projects/demo/workflow-output/views.json",
    ])
    # .cnd is not JSON; the derivable primary is views.json (PROBE test -s)
    assert step_artifact_rel(s) == "projects/demo/workflow-output/views.json"


def test_artifact_rel_none_for_dir_probe_or_shell():
    assert step_artifact_rel(_step(["PROBE: node orchestration/lib/mirror_probe.mjs projects/demo 10"])) is None
    assert step_artifact_rel(_step(["PROBE: bash orchestration/probes/connect.sh projects/demo"])) is None
    assert step_artifact_rel(_step([])) is None
    # a .json OUTSIDE workflow-output is not counted (e.g. content-load payload)
    assert step_artifact_rel(_step(["Run: extract_content.py --out orchestration/content/demo.content-load.json"])) is None


# ── read_json_provenance: in-file key, then sidecar ──────────────────────
def test_read_provenance_in_file(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"pages": [1], "_provenance": {"run_id": "run_x", "tool": "t"}}))
    assert read_json_provenance(p) == {"run_id": "run_x", "tool": "t"}


def test_read_provenance_sidecar(tmp_path):
    # artifact carries no in-file stamp but a sibling X.provenance.json does
    (tmp_path / "b.json").write_text(json.dumps({"pages": [1]}))
    (tmp_path / "b.provenance.json").write_text(json.dumps({"run_id": "run_side"}))
    assert read_json_provenance(tmp_path / "b.json") == {"run_id": "run_side"}


def test_read_provenance_none(tmp_path):
    (tmp_path / "c.json").write_text(json.dumps({"pages": [1]}))
    assert read_json_provenance(tmp_path / "c.json") is None
    assert read_json_provenance(tmp_path / "missing.json") is None


def test_read_provenance_corrupt_is_none(tmp_path):
    (tmp_path / "d.json").write_text("{not json")
    assert read_json_provenance(tmp_path / "d.json") is None


# ── step_provenance: reused / self / neither / guarded ───────────────────
def _run(tmp_path, run_id="run_this", project="demo"):
    return RunState(run_id=run_id, goal="g", repo_dir=str(tmp_path), model="m",
                    project=project, created_at=1.0, updated_at=1.0)


def _wo(tmp_path, project="demo"):
    wo = tmp_path / "projects" / project / "workflow-output"
    wo.mkdir(parents=True, exist_ok=True)
    return wo


def test_step_provenance_reused(tmp_path):
    wo = _wo(tmp_path)
    (wo / "page-inventory.json").write_text(json.dumps(
        {"pages": [1], "_provenance": {"run_id": "run_earlier", "generated_at": "2026-07-08T10:00:00Z"}}))
    run = _run(tmp_path)
    step = _step(["PROBE: test -s projects/demo/workflow-output/page-inventory.json"])
    out = step_provenance(run, step)
    assert out["found"] is True
    assert out["reused"] is True and out["self"] is False
    assert out["produced_by_run"] == "run_earlier"
    assert out["generated_at"] == "2026-07-08T10:00:00Z"


def test_step_provenance_self(tmp_path):
    wo = _wo(tmp_path)
    (wo / "component-manifest.json").write_text(json.dumps(
        {"components": [], "_provenance": {"run_id": "run_this"}}))
    run = _run(tmp_path)
    step = _step(["PROBE: test -s projects/demo/workflow-output/component-manifest.json"])
    out = step_provenance(run, step)
    assert out["self"] is True and out["reused"] is False
    assert out["produced_by_run"] == "run_this"


def test_step_provenance_unstamped_is_neither(tmp_path):
    # old pre-P0 artifact: exists, no stamp → neither reused nor self
    wo = _wo(tmp_path)
    (wo / "semantic-candidates.json").write_text(json.dumps({"components": [1]}))
    run = _run(tmp_path)
    step = _step(["PROBE: test -s projects/demo/workflow-output/semantic-candidates.json"])
    out = step_provenance(run, step)
    assert out["found"] is True
    assert out["reused"] is False and out["self"] is False
    assert out["produced_by_run"] is None


def test_step_provenance_not_derivable(tmp_path):
    run = _run(tmp_path)
    out = step_provenance(run, _step(["PROBE: bash orchestration/probes/connect.sh projects/demo"]))
    assert out["artifact"] is None and out["found"] is False


def test_step_provenance_missing_file(tmp_path):
    _wo(tmp_path)
    run = _run(tmp_path)
    step = _step(["PROBE: test -s projects/demo/workflow-output/page-inventory.json"])
    out = step_provenance(run, step)
    assert out["artifact"] == "projects/demo/workflow-output/page-inventory.json"
    assert out["found"] is False and out["reused"] is False


def test_step_provenance_traversal_guarded(tmp_path):
    # a step naming another project's artifact never reads across the boundary
    other = tmp_path / "projects" / "other" / "workflow-output"
    other.mkdir(parents=True)
    (other / "page-inventory.json").write_text(json.dumps({"_provenance": {"run_id": "x"}}))
    run = _run(tmp_path, project="demo")
    step = _step(["PROBE: test -s projects/other/workflow-output/page-inventory.json"])
    out = step_provenance(run, step)
    assert out["found"] is False and out["provenance"] is None


# ── route: GET /runs/{run_id}/provenance batches the map ─────────────────
def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(runs_routes.router)
    return TestClient(app)


def _run_with_steps(tmp_path):
    steps = [
        # reused: validates an earlier run's mirror
        StepState(id="step_connect", story_id="s1",
                  acceptance_criteria=["PROBE: test -s projects/demo/workflow-output/local-mirror/mirror.json"]),
        # self: produced this run
        StepState(id="step_group", story_id="s1",
                  acceptance_criteria=["PROBE: test -s projects/demo/workflow-output/component-manifest.json"]),
        # no derivable artifact → omitted from the map
        StepState(id="step_mirror", story_id="s1",
                  acceptance_criteria=["PROBE: node orchestration/lib/mirror_probe.mjs projects/demo 10"]),
    ]
    return RunState(run_id="run_this", goal="g", repo_dir=str(tmp_path), model="m",
                    project="demo", created_at=1.0, updated_at=1.0,
                    epics=[EpicState(id="e1", title="E", goal="g", stories=[
                        StoryState(id="s1", title="S", description="d", steps=steps)])])


def test_route_provenance_map(tmp_path, monkeypatch):
    wo = _wo(tmp_path)
    (wo / "local-mirror").mkdir()
    (wo / "local-mirror" / "mirror.json").write_text(json.dumps(
        {"pages": [1], "_provenance": {"run_id": "run_earlier", "generated_at": "2026-07-01T09:00:00Z"}}))
    (wo / "component-manifest.json").write_text(json.dumps(
        {"components": [], "_provenance": {"run_id": "run_this"}}))

    run = _run_with_steps(tmp_path)
    monkeypatch.setattr(runs_routes, "get_run", lambda rid: run if rid == "run_this" else None)

    resp = _client().get("/runs/run_this/provenance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run_this"
    # only the two steps with a derivable artifact are present (step_mirror omitted)
    assert set(body["steps"]) == {"step_connect", "step_group"}
    assert body["steps"]["step_connect"]["reused"] is True
    assert body["steps"]["step_connect"]["produced_by_run"] == "run_earlier"
    assert body["steps"]["step_connect"]["generated_at"] == "2026-07-01T09:00:00Z"
    assert body["steps"]["step_group"]["self"] is True
    assert body["steps"]["step_group"]["reused"] is False


def test_route_provenance_run_not_found(monkeypatch):
    monkeypatch.setattr(runs_routes, "get_run", lambda rid: None)

    async def _no_load(rid):
        return None

    monkeypatch.setattr(runs_routes, "load_run", _no_load)
    resp = _client().get("/runs/ghost/provenance")
    assert resp.status_code == 404
