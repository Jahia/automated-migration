from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "ORCHESTRATOR_"}

    opencode_port: int = 4096
    opencode_hostname: str = "127.0.0.1"
    opencode_model: str = "anthropic/claude-sonnet-4-5"

    db_path: str = "orchestrator.db"

    env_file: str = ".env.local"

    # Engine-level integrity belt (orchestration/probes/integrity.py): after a
    # content step's own probes pass, the engine diffs the live Jahia against the
    # pipeline artifacts as an ADDITIONAL verification. ON by default; set
    # ORCHESTRATOR_INTEGRITY=false to disable (kill-switch). Its own timeout in s.
    integrity: bool = True
    integrity_timeout: float = 120.0

    # Engine-executes-Run: doctrine (P5, load_content 2×600s read-loop incident).
    # A step whose acceptance_criteria carry `Run: <cmd>` lines has, at plan time,
    # a KNOWN deterministic command — it does not need an LLM to be executed. The
    # engine runs those lines ITSELF (same subprocess mechanism as PROBEs) BEFORE
    # any agent session. If they all pass, no agent is opened at all; if one fails
    # the agent is opened as a REPAIRER with the failure context appended. ON by
    # default; set ORCHESTRATOR_ENGINE_EXEC_RUN=false to disable (kill-switch —
    # same pattern as ORCHESTRATOR_INTEGRITY above), restoring the legacy path
    # where the agent is always sent the Run: lines as prose to execute itself.
    # Per-task_type timeouts (seconds): content steps get a long budget (MCP media
    # uploads, page trees), everything else the default.
    engine_exec_run: bool = True
    engine_exec_run_content_timeout: float = 3600.0
    engine_exec_run_default_timeout: float = 900.0

    github_token: str | None = None
    github_repo: str | None = None

    host: str = "0.0.0.0"
    port: int = 8001

    @property
    def opencode_base_url(self) -> str:
        return f"http://{self.opencode_hostname}:{self.opencode_port}"


settings = Settings()
