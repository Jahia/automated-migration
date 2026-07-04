from __future__ import annotations

import asyncio
import logging
import subprocess

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .github_client import GitHubClient
from .opencode_client import OpenCodeClient
from .opencode_events import OpenCodeEventListener
from .persistence import close_db, get_db
from .routes import content_progress, epics, events, runs, schema, stats, steps

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_opencode_process: subprocess.Popen | None = None


async def start_opencode_server() -> None:
    global _opencode_process
    log.info(f"Starting opencode serve on port {settings.opencode_port}...")
    _opencode_process = subprocess.Popen(
        ["opencode", "serve", "--port", str(settings.opencode_port), "--hostname", settings.opencode_hostname],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = OpenCodeClient()
    for i in range(30):
        try:
            health = await client.health()
            if health.get("healthy"):
                log.info("OpenCode server is ready")
                return
        except Exception:
            pass
        await asyncio.sleep(1)
    log.warning("OpenCode server did not become ready in 30s")


async def stop_opencode_server() -> None:
    global _opencode_process
    if _opencode_process:
        _opencode_process.terminate()
        try:
            _opencode_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _opencode_process.kill()
        _opencode_process = None
        log.info("OpenCode server stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_opencode_server()

    client = OpenCodeClient()
    event_listener = OpenCodeEventListener()

    app.state.opencode_client = client
    app.state.event_listener = event_listener
    app.state.github_client = GitHubClient()

    await event_listener.start()
    await get_db()

    ui_path = Path(__file__).parent / "ui"
    if ui_path.exists():
        app.mount("/app", StaticFiles(directory=str(ui_path), html=True), name="ui")

    yield

    await event_listener.stop()
    await close_db()
    await stop_opencode_server()


app = FastAPI(
    title="LLM Orchestration Loop",
    description="Orchestrateur LLM avec opencode serve",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schema.router, tags=["schema"])
app.include_router(runs.router, tags=["runs"])
app.include_router(steps.router, tags=["steps"])
app.include_router(epics.router, tags=["epics"])
app.include_router(events.router, tags=["events"])
app.include_router(stats.router, tags=["stats"])
app.include_router(content_progress.router, tags=["content-progress"])


@app.middleware("http")
async def spa_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/app/") and not path.startswith("/app/assets/"):
        ui_file = Path(__file__).parent / "ui" / "index.html"
        if ui_file.exists():
            return FileResponse(str(ui_file))
    return await call_next(request)


@app.get("/health")
async def health():
    try:
        client: OpenCodeClient = app.state.opencode_client
        oc_health = await client.health()
        return {"status": "ok", "opencode": oc_health}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}
