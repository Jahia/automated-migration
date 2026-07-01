from __future__ import annotations

import json

import aiosqlite

from .config import settings
from .models import RunState, RunStatus

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
    await db.commit()


async def save_run(run: RunState) -> None:
    db = await get_db()
    state_json = run.model_dump_json()
    await db.execute(
        """INSERT OR REPLACE INTO runs (run_id, goal, repo_dir, model, status, state_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (run.run_id, run.goal, run.repo_dir, run.model, run.status.value, state_json, run.created_at, run.updated_at),
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
    return run


async def list_runs() -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT run_id, goal, status, created_at, updated_at FROM runs ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    return [
        {
            "run_id": r["run_id"],
            "goal": r["goal"],
            "status": r["status"],
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


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
