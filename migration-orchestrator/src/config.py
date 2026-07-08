from __future__ import annotations

from pydantic_settings import BaseSettings

# ── Direct LLM defaults (P5.5: opencode dropped) ─────────────────────────────
# Provider-agnostic by construction (Julian's non-negotiable): everything flows
# through base_url / model / key. The ONLY provider-specific bits here are the
# DEFAULTS — the current DeepSeek runs' OpenAI-compatible endpoint and model.
# The API KEY is never a default and never appears in source; it is read from
# ORCHESTRATOR_LLM_API_KEY in the environment (or migration-orchestrator/.env).
DEFAULT_LLM_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_LLM_MODEL = "deepseek-v4-flash"


class Settings(BaseSettings):
    # env_file loads migration-orchestrator/.env for the ORCHESTRATOR_* vars —
    # notably ORCHESTRATOR_LLM_API_KEY (gitignored; see .env / .env.example). The
    # process environment still overrides the file.
    model_config = {"env_prefix": "ORCHESTRATOR_", "env_file": ".env", "extra": "ignore"}

    db_path: str = "orchestrator.db"

    # Path (relative to repo_dir) to the SITE credentials env file that PROBEs and
    # Run:/tool subprocesses source ($JAHIA_URL/$JAHIA_USER/$JAHIA_PASS). Distinct
    # from the ORCHESTRATOR_* dotenv above (model_config.env_file) — that one
    # configures the engine, this one configures the migration target.
    env_file: str = ".env.local"

    # ── Direct LLM client (OpenAI-compatible; replaces opencode) ─────────────
    # Provider stays swappable: point these three at any OpenAI-compatible API.
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_model: str = DEFAULT_LLM_MODEL
    llm_api_key: str | None = None
    # Kept for out-of-engine pipeline scripts and any future in-engine judgment
    # role. P5.5b: the engine's control loop makes NO LLM calls (DeepSeek left the
    # loop), so these knobs are currently unused by the orchestrator itself.
    llm_timeout: float = 180.0
    llm_max_retries: int = 3

    # Engine-level integrity belt (orchestration/probes/integrity.py): after a
    # content step's own probes pass, the engine diffs the live Jahia against the
    # pipeline artifacts as an ADDITIONAL verification. ON by default; set
    # ORCHESTRATOR_INTEGRITY=false to disable (kill-switch). Its own timeout in s.
    integrity: bool = True
    integrity_timeout: float = 120.0

    # Engine-executes-Run: doctrine (P5, load_content 2×600s read-loop incident;
    # P5.5b: no LLM in the loop at all). A step whose acceptance_criteria carry
    # `Run: <cmd>` lines has, at plan time, a KNOWN deterministic command — the
    # engine runs those lines ITSELF (same subprocess mechanism as PROBEs). If they
    # all pass, a synthetic agent="engine" result is fabricated and the PROBEs
    # judge; if one fails the STEP fails with the failure context stashed
    # (command, exit code, stderr/stdout tails) — retries re-run it, and once
    # exhausted it parks as decision_pending (retry / repatch / rollback). ON by
    # default; set ORCHESTRATOR_ENGINE_EXEC_RUN=false to disable (kill-switch —
    # same pattern as ORCHESTRATOR_INTEGRITY above): Run: lines are then NOT
    # executed and only the PROBEs judge the step.
    # Per-task_type timeouts (seconds): content steps get a long budget (MCP media
    # uploads, page trees), everything else the default.
    engine_exec_run: bool = True
    engine_exec_run_content_timeout: float = 3600.0
    engine_exec_run_default_timeout: float = 900.0

    # P5: per-run structured audit JSONL directory (audit.py RunAuditLogger).
    # None (default) resolves to a persistent path anchored on the package dir
    # (migration-orchestrator/logs/audit) — override for ops (e.g. a bigger disk)
    # with ORCHESTRATOR_AUDIT_DIR.
    audit_dir: str | None = None

    github_token: str | None = None
    github_repo: str | None = None

    host: str = "0.0.0.0"
    port: int = 8001

    @property
    def llm_configured(self) -> bool:
        """True when an API key is present — the engine can talk to the LLM."""
        return bool(self.llm_api_key)


settings = Settings()
