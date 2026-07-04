from __future__ import annotations

import logging

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .github_client import GitHubClient
from .llm_client import LLMClient
from .persistence import close_db, get_db
from .routes import content_progress, epics, events, runs, schema, stats, steps

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P5.5b: DeepSeek exited the CONTROL loop. The engine executes deterministically
    # (Run: lines + PROBEs), approves epics by rule, and parks on decision_pending —
    # it makes NO LLM calls in nominal operation. The LLMClient is still constructed
    # (provider-agnostic config compat; a future judgment role could return) and
    # shared as app.state.llm_client, but no call site in the orchestrator uses it.
    client = LLMClient()
    if not client.configured:
        log.info(
            "ORCHESTRATOR_LLM_API_KEY is not set — fine: the engine makes no LLM calls. "
            "The key is only for out-of-engine pipeline scripts (group_llm / vision)."
        )
    else:
        log.info(f"LLM client configured (pipeline-only; engine makes no LLM calls): "
                 f"model={client.model} base_url={client.base_url}")

    app.state.llm_client = client
    # event_listener is a P4 vestige; the routes still read app.state.event_listener
    # and thread it through, but it is unused (None) now that there is no SSE feed
    # from an agent runtime to subscribe to.
    app.state.event_listener = None
    app.state.github_client = GitHubClient()

    await get_db()

    ui_path = Path(__file__).parent / "ui"
    if ui_path.exists():
        app.mount("/app", StaticFiles(directory=str(ui_path), html=True), name="ui")

    yield

    await close_db()
    await client.aclose()


app = FastAPI(
    title="LLM Orchestration Loop",
    description="Orchestrateur LLM — API directe OpenAI-compatible (DeepSeek par défaut)",
    version="0.2.0",
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
    # Never leaks the key — only whether one is configured, plus the model/base_url.
    # P5.5b: DeepSeek exited the control loop entirely — the ENGINE makes NO LLM
    # calls in nominal operation (epic approval is deterministic, retries+idempotence
    # cover transients, and there is no repair agent). `configured` stays for the
    # PIPELINE scripts (group_llm / vision) that still use an LLM outside the engine;
    # `role: "pipeline-only"` says so plainly so the field isn't read as "the engine
    # will call the LLM".
    return {
        "status": "ok",
        "llm": {
            "configured": settings.llm_configured,
            "model": settings.llm_model,
            "base_url": settings.llm_base_url,
            "role": "pipeline-only",
            "note": "engine makes no LLM calls; key is for out-of-engine pipeline scripts only",
        },
    }
