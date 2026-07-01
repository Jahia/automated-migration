from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "ORCHESTRATOR_"}

    opencode_port: int = 4096
    opencode_hostname: str = "127.0.0.1"
    opencode_model: str = "anthropic/claude-sonnet-4-5"

    db_path: str = "orchestrator.db"

    github_token: str | None = None
    github_repo: str | None = None

    host: str = "0.0.0.0"
    port: int = 8001

    @property
    def opencode_base_url(self) -> str:
        return f"http://{self.opencode_hostname}:{self.opencode_port}"


settings = Settings()
