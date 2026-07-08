"""Project modeling tests (P1): "project" is modeled, not re-scanned.

RunState.project (bare name) is derived ONCE (state.derive_project) at plan
build, persisted as a runs.project column (schema-migrated + backfilled on old
DBs), backfilled onto old blobs at load, and short-circuits every consumer that
used to re-scan step inputs (migration_control.project_path, llm_cost.project_of,
verifier.derive_site). GET /projects groups the run list per project with the
same live-truth status merge as GET /runs, plus zero-run project directories.
These tests fabricate everything under tmp_path / temp DBs — nothing touches the
live orchestrator.db or projects/.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import aiosqlite
import pytest

from src import persistence
from src.config import settings
from src.llm_cost import project_of
from src.migration_control import project_path, workflow_output_dir
from src.models import EpicInput, PlanInput, RunState, RunStatus, StepInput, StepState, StoryInput
from src.routes import content_progress as cp
from src.routes import projects as proj_routes
from src.routes import runs as runs_routes
from src.state import build_run_state, derive_project, normalize_project
from src.verifier import derive_site, integrity_command


def run_async(coro):
    async def _wrap():
        try:
            return await coro
        finally:
            await persistence.close_db()
    return asyncio.run(_wrap())


def _mini_plan(project="demo"):
    return PlanInput(
        goal="g", repo_dir="/tmp",
        epics=[EpicInput(id="e1", title="E", goal="g", stories=[
            StoryInput(id="s1", title="S", description="d", steps=[
                StepInput(id="st1", title="t", task_type="verify",
                          inputs={"project_path": f"projects/{project}", "project": project},
                          acceptance_criteria=["PROBE: true"]),
            ]),
        ])],
    )


# ── normalize_project: every inputs shape → the BARE name ────────────────
@pytest.mark.parametrize("raw,expected", [
    ("discoverasr", "discoverasr"),
    ("projects/discoverasr", "discoverasr"),
    ("projects/discoverasr/", "discoverasr"),
    ("  projects/sial-paris  ", "sial-paris"),
    ("/abs/checkout/projects/foo", "foo"),
    ("", None),
    (None, None),
    ("/", None),
])
def test_normalize_project(raw, expected):
    assert normalize_project(raw) == expected


# ── derive_project: models AND raw state_json dicts ──────────────────────
def test_derive_project_over_raw_dicts():
    epics = [{"stories": [{"steps": [
        {"inputs": {}},
        {"inputs": {"project_path": "projects/acme"}},
    ]}]}]
    assert derive_project(epics) == "acme"


def test_derive_project_prefers_project_over_project_path():
    epics = [{"stories": [{"steps": [
        {"inputs": {"project": "bare", "project_path": "projects/other"}},
    ]}]}]
    assert derive_project(epics) == "bare"


def test_derive_project_empty_inputs_is_none():
    assert derive_project([]) is None
    assert derive_project(None) is None
    assert derive_project([{"stories": [{"steps": [{"inputs": {}}]}]}]) is None


def test_build_run_state_stamps_project():
    run = build_run_state(_mini_plan("demo"))
    assert run.project == "demo"


def test_old_blob_without_project_still_deserializes():
    run = build_run_state(_mini_plan("demo"))
    blob = json.loads(run.model_dump_json())
    blob.pop("project")  # an OLD persisted blob predating the field
    old = RunState.model_validate(blob)
    assert old.project is None  # deserializes; load_run backfills it


# ── consumers short-circuit on run.project, scan stays for old blobs ─────
def test_project_path_short_circuits_then_falls_back():
    run = build_run_state(_mini_plan("demo"))
    assert project_path(run) == "projects/demo"
    assert str(workflow_output_dir(run)).endswith("projects/demo/workflow-output")
    run.project = None  # old blob, no backfill → legacy step-inputs scan
    assert project_path(run) == "projects/demo"


def test_project_of_prefers_step_inputs_then_modeled_then_scan():
    run = build_run_state(_mini_plan("demo"))
    step = run.epics[0].stories[0].steps[0]
    assert project_of(run, step) == "demo"   # step inputs stay authoritative
    assert project_of(run, None) == "demo"   # modeled run.project
    run.project = None
    assert project_of(run, None) == "demo"   # legacy run-wide scan


def test_derive_site_modeled_project_fills_the_gap():
    bare = StepState(id="step_content_load", story_id="s1", task_type="content", inputs={})
    assert derive_site(bare) is None
    assert derive_site(bare, "demo") == "demo"
    # step inputs stay authoritative when present (exact arg shape the plan chose)
    stamped = StepState(id="step_content_load", story_id="s1", task_type="content",
                        inputs={"project": "projects/other"})
    assert derive_site(stamped, "demo") == "other"
    assert integrity_command(stamped, "demo") == (
        "python3 orchestration/probes/integrity.py projects/other other --phase step_content_load")
    # modeled fallback is a bare name → re-anchored under projects/ (integrity.py
    # joins its project_path arg under the repo root; a bare name would 404)
    assert integrity_command(bare, "demo") == (
        "python3 orchestration/probes/integrity.py projects/demo demo --phase step_content_load")


# ── persistence: schema migration + backfill on an OLD-schema DB ─────────
OLD_SCHEMA = """CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    repo_dir TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    state_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)"""


def _old_blob(inputs):
    """A minimal pre-P1 state_json blob (no top-level "project" key)."""
    return json.dumps({"run_id": "x", "goal": "g", "repo_dir": "/tmp", "model": "m",
                       "status": "completed", "created_at": 1.0, "updated_at": 2.0,
                       "epics": [{"id": "e1", "stories": [{"id": "s1", "steps": [
                           {"id": "st1", "inputs": inputs}]}]}]})


def test_init_tables_migrates_and_backfills(tmp_path):
    async def scenario():
        conn = await aiosqlite.connect(tmp_path / "old.db")
        conn.row_factory = aiosqlite.Row
        try:
            await conn.execute(OLD_SCHEMA)
            await conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                ("run_old", "g", "/tmp", "m", "completed",
                 _old_blob({"project_path": "projects/discoverasr"}), 1.0, 2.0))
            await conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                ("run_bare", "g", "/tmp", "m", "completed",
                 _old_blob({"project": "acquia"}), 3.0, 4.0))
            # projectless + corrupt blobs must not block the migration
            await conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                ("run_none", "g", "/tmp", "m", "completed", _old_blob({}), 5.0, 6.0))
            await conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                ("run_corrupt", "g", "/tmp", "m", "completed", "{not json", 7.0, 8.0))
            await conn.commit()

            await persistence.init_tables(conn)   # ALTER + backfill
            await persistence.init_tables(conn)   # idempotent on second pass

            cur = await conn.execute("SELECT run_id, project, state_json FROM runs")
            rows = {r["run_id"]: r for r in await cur.fetchall()}
            assert rows["run_old"]["project"] == "discoverasr"
            assert rows["run_bare"]["project"] == "acquia"
            assert rows["run_none"]["project"] is None
            assert rows["run_corrupt"]["project"] is None
            # only the COLUMN was written — old blobs stay byte-identical
            assert rows["run_old"]["state_json"] == _old_blob({"project_path": "projects/discoverasr"})
        finally:
            await conn.close()
    asyncio.run(scenario())


def test_save_list_load_round_trip_carries_project(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
        run = build_run_state(_mini_plan("demo"))
        await persistence.save_run(run)
        rows = await persistence.list_runs()
        assert rows[0]["run_id"] == run.run_id
        assert rows[0]["project"] == "demo"
        loaded = await persistence.load_run(run.run_id)
        assert loaded.project == "demo"
    run_async(scenario())


def test_load_run_backfills_old_blob_project(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(settings, "db_path", str(tmp_path / "t2.db"))
        run = build_run_state(_mini_plan("demo"))
        blob = json.loads(run.model_dump_json())
        blob.pop("project")  # simulate a pre-P1 persisted blob
        db = await persistence.get_db()
        await db.execute(
            """INSERT INTO runs (run_id, goal, repo_dir, model, status, project, state_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (run.run_id, run.goal, run.repo_dir, run.model, "completed", None,
             json.dumps(blob), run.created_at, run.updated_at))
        await db.commit()
        loaded = await persistence.load_run(run.run_id)
        assert loaded.project == "demo"  # derived once at load
    run_async(scenario())


# ── GET /projects: grouping, live-truth status, zero-run directories ─────
def _projects_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(proj_routes.router)
    return TestClient(app)


def test_get_projects_grouping(tmp_path, monkeypatch):
    rows = [
        {"run_id": "run_3", "goal": "g3", "status": "running", "project": "alpha",
         "created_at": 3000.0, "updated_at": 3100.0},
        {"run_id": "run_2", "goal": "g2", "status": "completed", "project": "alpha",
         "created_at": 2000.0, "updated_at": 2100.0},
        {"run_id": "run_1", "goal": "g1", "status": "running", "project": "beta",
         "created_at": 1000.0, "updated_at": 1100.0},
        {"run_id": "run_0", "goal": "g0", "status": "failed", "project": None,
         "created_at": 500.0, "updated_at": 600.0},
    ]

    async def _fake_list_runs():
        return [dict(r) for r in rows]

    monkeypatch.setattr(proj_routes, "list_runs", _fake_list_runs)
    # run_3 has a live loop → running; run_1 is persisted 'running' with no loop → paused
    live = {"run_3": SimpleNamespace(status=RunStatus.running)}
    monkeypatch.setattr(proj_routes, "get_run", lambda rid: live.get(rid))
    monkeypatch.setattr(cp, "_harness_root", lambda: tmp_path)
    (tmp_path / "projects" / "gamma").mkdir(parents=True)  # zero-run project dir
    (tmp_path / "projects" / "alpha").mkdir()              # has runs → not duplicated
    (tmp_path / "projects" / ".hidden").mkdir()            # hidden → excluded
    (tmp_path / "projects" / "notes.txt").write_text("x")  # file → excluded

    resp = _projects_client().get("/projects")
    assert resp.status_code == 200
    body = resp.json()
    # most recent activity first; zero-run dirs (no activity) last
    assert [g["project"] for g in body] == ["alpha", "beta", None, "gamma"]

    alpha = body[0]
    assert alpha["run_count"] == 2
    assert alpha["active_run_id"] == "run_3"
    assert alpha["last_created_at"] == 3000.0
    assert [r["run_id"] for r in alpha["runs"]] == ["run_3", "run_2"]  # created_at desc
    assert alpha["runs"][0]["status"] == "running"
    assert alpha["runs"][0]["project"] == "alpha"

    beta = body[1]
    assert beta["active_run_id"] is None
    assert beta["runs"][0]["status"] == "paused"  # engine restarted → not active

    gamma = body[3]
    assert gamma == {"project": "gamma", "run_count": 0, "active_run_id": None,
                     "last_created_at": None, "runs": []}


def test_get_projects_no_projects_dir(monkeypatch, tmp_path):
    async def _fake_list_runs():
        return []

    monkeypatch.setattr(proj_routes, "list_runs", _fake_list_runs)
    monkeypatch.setattr(proj_routes, "get_run", lambda rid: None)
    monkeypatch.setattr(cp, "_harness_root", lambda: tmp_path / "nowhere")
    resp = _projects_client().get("/projects")
    assert resp.status_code == 200
    assert resp.json() == []


# ── POST /runs|/migrations concurrent-run warning (helper) ───────────────
def test_concurrent_project_warnings(monkeypatch):
    run = build_run_state(_mini_plan("alpha"))
    rows = [
        {"run_id": run.run_id, "goal": "g", "status": "created", "project": "alpha",
         "created_at": 1.0, "updated_at": 1.0},  # the run being created: ignored
        {"run_id": "run_live", "goal": "g", "status": "running", "project": "alpha",
         "created_at": 1.0, "updated_at": 1.0},  # live loop → WARN
        {"run_id": "run_ghost", "goal": "g", "status": "running", "project": "alpha",
         "created_at": 1.0, "updated_at": 1.0},  # no loop → effectively paused
        {"run_id": "run_other", "goal": "g", "status": "running", "project": "beta",
         "created_at": 1.0, "updated_at": 1.0},  # other project
    ]

    async def _fake_list_runs():
        return [dict(r) for r in rows]

    monkeypatch.setattr(runs_routes, "list_runs", _fake_list_runs)
    live = {"run_live": SimpleNamespace(status=RunStatus.running)}
    monkeypatch.setattr(runs_routes, "get_run", lambda rid: live.get(rid))

    warnings = asyncio.run(runs_routes._concurrent_project_warnings(run))
    assert len(warnings) == 1
    assert "run_live" in warnings[0] and "alpha" in warnings[0]

    run.project = None  # projectless run → never warns
    assert asyncio.run(runs_routes._concurrent_project_warnings(run)) == []
