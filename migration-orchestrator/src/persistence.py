from __future__ import annotations

import json
import logging
import time

import aiosqlite

from .config import settings
from .models import RunState, RunStatus
from .state import derive_project

log = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(settings.db_path)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await init_tables(_db)
    return _db


async def init_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            repo_dir TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            project TEXT,
            state_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            epic_id TEXT,
            story_id TEXT,
            step_id TEXT,
            type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            timestamp REAL NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        )
    """)
    await _migrate_runs_project(db)
    await _mark_interrupted_runs(db)
    await db.commit()


async def _migrate_runs_project(db: aiosqlite.Connection) -> None:
    """Schema migration (P1): DBs created before the `project` column get it
    ALTERed in, then BACKFILLED from each row's state_json via derive_project.
    Only the COLUMN is written — state_json blobs stay byte-identical, so old
    runs keep deserializing exactly as before (load_run backfills the model)."""
    cursor = await db.execute("PRAGMA table_info(runs)")
    # r[1] = column name: works with both the aiosqlite.Row factory and the
    # default tuple factory (tests call init_tables on their own connection).
    cols = {r[1] for r in await cursor.fetchall()}
    if "project" in cols:
        return
    await db.execute("ALTER TABLE runs ADD COLUMN project TEXT")
    cursor = await db.execute("SELECT run_id, state_json FROM runs WHERE project IS NULL")
    for run_id, state_json in [(r[0], r[1]) for r in await cursor.fetchall()]:
        try:
            project = derive_project(json.loads(state_json).get("epics"))
        except (ValueError, TypeError, AttributeError):
            project = None  # a corrupt/foreign blob never blocks startup
        if project:
            await db.execute("UPDATE runs SET project = ? WHERE run_id = ?", (project, run_id))


async def _mark_interrupted_runs(db: aiosqlite.Connection) -> None:
    """Boot-time integrity pass (P5 observability): a run persisted with
    status='running' in a FRESH process has no live asyncio loop — the engine was
    killed/crashed mid-run (or the host rebooted) rather than exiting cleanly
    through _run_loop's `finally` block. GET /runs and GET /projects already
    normalize this to 'paused' for DISPLAY (a mem-less 'running' row reads as
    'paused'), but the stored row keeps lying forever unless something fixes it.
    Flip it to 'interrupted' (distinct from an operator-initiated 'paused' — worth
    flagging, not silently conflated) and stamp BOTH the state_json blob
    (status + a trace note) and the status column, so every consumer agrees
    whether it reads the column (list_runs) or the blob (load_run). A row whose
    blob doesn't round-trip as JSON still gets its column fixed — a corrupt/
    foreign blob must never block startup (same tolerance as
    _migrate_runs_project). Runs AFTER the project-column migration by design
    (the caller order in init_tables), so a pre-P1 blob has both fixes applied
    together at the same boot."""
    cursor = await db.execute("SELECT run_id, state_json FROM runs WHERE status = 'running'")
    rows = [(r[0], r[1]) for r in await cursor.fetchall()]
    if not rows:
        return
    note = "engine restarted while this run was 'running' — no live process found at boot"
    now = time.time() * 1000
    for run_id, state_json in rows:
        new_state_json = None
        try:
            blob = json.loads(state_json)
            blob["status"] = "interrupted"
            trace = blob.get("trace")
            if not isinstance(trace, list):
                trace = []
            trace.append({
                "seq": len(trace) + 1, "timestamp": now, "type": "run_interrupted",
                "step_id": None, "story_id": None, "epic_id": None,
                "payload": {"note": note},
            })
            blob["trace"] = trace
            new_state_json = json.dumps(blob)
        except (ValueError, TypeError, AttributeError, KeyError):
            pass  # corrupt/foreign blob: fix the column only, never block startup
        if new_state_json is not None:
            await db.execute(
                "UPDATE runs SET status = 'interrupted', state_json = ? WHERE run_id = ?",
                (new_state_json, run_id))
        else:
            await db.execute("UPDATE runs SET status = 'interrupted' WHERE run_id = ?", (run_id,))
        await db.execute(
            """INSERT INTO events (run_id, epic_id, story_id, step_id, type, payload_json, timestamp)
               VALUES (?, NULL, NULL, NULL, 'run_interrupted', ?, ?)""",
            (run_id, json.dumps({"note": note}), now),
        )
        log.warning(f"Run {run_id}: was 'running' at boot with no live process — marked interrupted")


async def save_run(run: RunState) -> None:
    db = await get_db()
    state_json = run.model_dump_json()
    await db.execute(
        """INSERT OR REPLACE INTO runs (run_id, goal, repo_dir, model, status, project, state_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run.run_id, run.goal, run.repo_dir, run.model, run.status.value, run.project, state_json, run.created_at, run.updated_at),
    )
    await db.commit()


async def load_run(run_id: str) -> RunState | None:
    db = await get_db()
    cursor = await db.execute("SELECT state_json FROM runs WHERE run_id = ?", (run_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    run = RunState.model_validate_json(row["state_json"])
    if run.status.value == "running":
        run.status = RunStatus.paused
    if run.project is None:
        # Old blobs predate the modeled project — derive once at load so every
        # consumer (routes, ledger, integrity belt) short-circuits uniformly.
        run.project = derive_project(run.epics)
    return run


async def list_runs() -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT run_id, goal, status, project, created_at, updated_at FROM runs ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    return [
        {
            "run_id": r["run_id"],
            "goal": r["goal"],
            "status": r["status"],
            "project": r["project"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


async def delete_run(run_id: str) -> bool:
    """Permanently delete a single run and its events. Returns True if a row was
    actually removed (i.e. the run existed in the database)."""
    db = await get_db()
    await db.execute("DELETE FROM events WHERE run_id = ?", (run_id,))
    cursor = await db.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
    await db.commit()
    return cursor.rowcount > 0


async def delete_finished_runs() -> list[str]:
    """Delete every run that is no longer active (completed/failed/aborted) along
    with its events, and return the deleted run ids. Active runs
    (created/running/paused) are left untouched."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT run_id FROM runs WHERE status IN ('completed', 'failed', 'aborted')"
    )
    ids = [r["run_id"] for r in await cursor.fetchall()]
    for rid in ids:
        await db.execute("DELETE FROM events WHERE run_id = ?", (rid,))
    await db.execute(
        "DELETE FROM runs WHERE status IN ('completed', 'failed', 'aborted')"
    )
    await db.commit()
    return ids


async def save_event(run_id: str, event_type: str, payload: dict, *, epic_id: str | None = None, story_id: str | None = None, step_id: str | None = None) -> None:
    import time

    db = await get_db()
    await db.execute(
        """INSERT INTO events (run_id, epic_id, story_id, step_id, type, payload_json, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_id, epic_id, story_id, step_id, event_type, json.dumps(payload), time.time() * 1000),
    )
    await db.commit()


async def list_events(run_id: str, limit: int = 50, before_id: int | None = None) -> list[dict]:
    """Newest-first page of a run's persisted `events` rows (P5 observability):
    the append-only table every notify_sse call (plus a few direct save_event
    calls — gate_decision, rollback, rerun_step, decision) writes to, but which no
    route read until GET /runs/{run_id}/events/history. Durable across engine
    restarts, unlike the live SSE stream at GET /runs/{run_id}/events
    (routes/events.py — a subscriber only sees events emitted while connected).
    Paginate older pages with before_id=<the oldest "id" from the previous page>
    (strictly less-than, so pages never overlap)."""
    db = await get_db()
    if before_id is not None:
        cursor = await db.execute(
            """SELECT id, run_id, epic_id, story_id, step_id, type, payload_json, timestamp
               FROM events WHERE run_id = ? AND id < ? ORDER BY id DESC LIMIT ?""",
            (run_id, before_id, limit),
        )
    else:
        cursor = await db.execute(
            """SELECT id, run_id, epic_id, story_id, step_id, type, payload_json, timestamp
               FROM events WHERE run_id = ? ORDER BY id DESC LIMIT ?""",
            (run_id, limit),
        )
    rows = await cursor.fetchall()
    out = []
    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
        except (TypeError, ValueError):
            payload = None
        out.append({
            "id": r["id"], "run_id": r["run_id"],
            "epic_id": r["epic_id"], "story_id": r["story_id"], "step_id": r["step_id"],
            "type": r["type"], "payload": payload, "timestamp": r["timestamp"],
        })
    return out


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
