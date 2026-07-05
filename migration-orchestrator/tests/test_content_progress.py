"""Read-only /projects/{project}/content-progress endpoint tests (Julian, 2026-07-04).

The endpoint is a PURE FILE READER over the content_watch.sh ticker
(content-progress.jsonl) + a light integrity-report.json summary — no Jahia call.
These tests fabricate a fake harness root under tmp_path (monkeypatching
_harness_root) so nothing touches the live repo, and drive both the pure reader
and the route (path-traversal / 404 / limit) through it.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

import src.routes.content_progress as cp


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """A throwaway repo root; returns the projects/ dir for convenience."""
    monkeypatch.setattr(cp, "_harness_root", lambda: tmp_path)
    projects = tmp_path / "projects"
    projects.mkdir()
    return projects


def _make_project(projects, name="demo", *, ticks=None, report=None):
    wo = projects / name / "workflow-output"
    wo.mkdir(parents=True)
    if ticks is not None:
        with open(wo / "content-progress.jsonl", "w") as f:
            for t in ticks:
                f.write(json.dumps(t) + "\n")
    if report is not None:
        with open(wo / "integrity-report.json", "w") as f:
            json.dump(report, f)
    return wo


def _tick(i, expected=100):
    return {"ts": f"2026-07-04T08:{i:02d}:00Z", "expected": expected, "created": i,
            "pct": round(100.0 * i / expected, 1), "pagesStarted": i, "pagesTotal": 20, "media": i}


# ── pure reader: files present ──────────────────────────────────────────
def test_reads_ticks_and_report(fake_root):
    report = {"ranAt": "2026-07-04T08:20:59Z", "phase": "step_content_load",
              "mismatches": [{"kind": "x"}, {"kind": "y"}],
              "sections": {"pages": {"expectedCount": 20, "actualCount": 5, "missing": []}}}
    _make_project(fake_root, ticks=[_tick(1), _tick(2), _tick(3)], report=report)

    out = cp.read_content_progress("demo")
    assert out["project"] == "demo"
    assert len(out["ticks"]) == 3
    assert out["latest"]["created"] == 3
    assert out["report"]["phase"] == "step_content_load"
    assert out["report"]["mismatchCount"] == 2
    assert out["report"]["pages"]["expectedCount"] == 20


# ── pure reader: files absent but project exists → empty payload ─────────
def test_project_exists_no_files(fake_root):
    (fake_root / "demo" / "workflow-output").mkdir(parents=True)
    out = cp.read_content_progress("demo")
    assert out == {"project": "demo", "ticks": [], "latest": None, "report": None}


def test_project_dir_no_workflow_output(fake_root):
    # project dir exists (valid) but has no workflow-output subdir yet
    (fake_root / "demo").mkdir()
    out = cp.read_content_progress("demo")
    assert out["ticks"] == [] and out["latest"] is None and out["report"] is None


# ── pure reader: missing project → 404 ──────────────────────────────────
def test_missing_project_raises_404(fake_root):
    with pytest.raises(HTTPException) as ei:
        cp.read_content_progress("nope")
    assert ei.value.status_code == 404


# ── limit truncates to the LAST N ticks ─────────────────────────────────
def test_limit_returns_last_n(fake_root):
    _make_project(fake_root, ticks=[_tick(i) for i in range(1, 11)])
    out = cp.read_content_progress("demo", limit=3)
    assert [t["created"] for t in out["ticks"]] == [8, 9, 10]
    assert out["latest"]["created"] == 10


def test_limit_zero_or_negative_returns_all(fake_root):
    _make_project(fake_root, ticks=[_tick(i) for i in range(1, 6)])
    assert len(cp.read_content_progress("demo", limit=0)["ticks"]) == 5
    assert len(cp.read_content_progress("demo", limit=-1)["ticks"]) == 5


# ── corrupt / blank JSONL lines are skipped, not fatal ──────────────────
def test_corrupt_lines_skipped(fake_root):
    wo = (fake_root / "demo" / "workflow-output")
    wo.mkdir(parents=True)
    with open(wo / "content-progress.jsonl", "w") as f:
        f.write(json.dumps(_tick(1)) + "\n")
        f.write("\n")                       # blank line
        f.write('{"ts": "half-written"\n')  # corrupt/half-flushed line
        f.write(json.dumps(_tick(2)) + "\n")
    out = cp.read_content_progress("demo")
    assert [t["created"] for t in out["ticks"]] == [1, 2]


# ── report summary drops the heavy blob, keeps only the light fields ────
def test_report_summary_is_light(fake_root):
    report = {"ranAt": "T", "phase": "step_content_load", "mismatches": [],
              "sections": {"pages": {"expectedCount": 3}, "instances": {"pages": {"a": 1}}},
              "checks": {"pages": True}, "jahiaUrl": "http://x"}
    _make_project(fake_root, ticks=[_tick(1)], report=report)
    r = cp.read_content_progress("demo")["report"]
    assert set(r.keys()) == {"ranAt", "phase", "mismatchCount", "pages"}
    assert r["mismatchCount"] == 0
    assert "instances" not in r  # heavy per-page section not leaked


def test_report_missing_pages_section_is_none(fake_root):
    report = {"ranAt": "T", "phase": "step_pages", "mismatches": [],
              "sections": {"instances": {"pages": {}}}}
    _make_project(fake_root, ticks=[], report=report)
    r = cp.read_content_progress("demo")["report"]
    assert r["pages"] is None
    assert r["phase"] == "step_pages"


# ── project-name validation (path traversal defence) ────────────────────
@pytest.mark.parametrize("bad", ["..", ".", "../secrets", "a/b", "/etc/passwd",
                                 "", "a\\b", "a\x00b"])
def test_invalid_project_names_rejected(bad):
    assert cp._valid_project(bad) is False


@pytest.mark.parametrize("good", ["discoverasr", "acquia-drupal", "sial-paris", "demo_1"])
def test_valid_project_names_accepted(good):
    assert cp._valid_project(good) is True


# ── route-level: path traversal → 400, missing → 404, happy → 200 ───────
def _client():
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(cp.router)
    return TestClient(app)


def test_route_rejects_traversal(fake_root):
    client = _client()
    # a traversal segment never resolves to the endpoint's {project} as a bare name;
    # an encoded one reaching the handler is rejected 400 by _valid_project.
    resp = client.get("/projects/..%2F..%2Fetc/content-progress")
    assert resp.status_code in (400, 404)


def test_route_dotdot_segment_400(fake_root):
    client = _client()
    resp = client.get("/projects/../content-progress")
    # Starlette collapses '..' in the path; either it never matches (404) or the
    # handler rejects it (400) — never a 200 that reads outside projects/.
    assert resp.status_code in (400, 404)


def test_route_missing_project_404(fake_root):
    resp = _client().get("/projects/ghost/content-progress")
    assert resp.status_code == 404


def test_route_happy_path_200(fake_root):
    _make_project(fake_root, name="discoverasr",
                  ticks=[_tick(1), _tick(2)],
                  report={"ranAt": "T", "phase": "step_content_load", "mismatches": [],
                          "sections": {"pages": {"expectedCount": 20}}})
    resp = _client().get("/projects/discoverasr/content-progress?limit=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project"] == "discoverasr"
    assert len(body["ticks"]) == 1
    assert body["latest"]["created"] == 2
    assert body["report"]["phase"] == "step_content_load"
