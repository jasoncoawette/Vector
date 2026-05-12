from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


SECRET_FIELDS = frozenset(
    {
        "anthropic_api_key",
        "elevenlabs_api_key",
        "deepgram_api_key",
        "backend_bearer",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="VECTOR_", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 7777
    workspace: Path = Path.home() / "VectorWorkspace"
    build_hash: str = "dev"

    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    deepgram_api_key: str = ""
    backend_bearer: str = ""
    elevenlabs_voice_id: str = "default"
    linear_api_key: str = ""

    brain_model_hot: str = "claude-sonnet-4-6"
    brain_model_hard: str = "claude-opus-4-7"

    max_parallel_agents: int = 3
    turn_timeout_s: int = 30
    loop_call_cap: int = 5

    safe_browser_hosts: tuple[str, ...] = Field(
        default=(
            "github.com",
            "linear.app",
            "mail.google.com",
            "sam.gov",
            "afwerx.af.mil",
            "dsip.dtic.mil",
        )
    )

    def redacted(self) -> dict:
        data = self.model_dump()
        for key in SECRET_FIELDS:
            if data.get(key):
                data[key] = "***redacted***"
            else:
                data[key] = ""
        data["workspace"] = str(data["workspace"])
        data["safe_browser_hosts"] = list(data["safe_browser_hosts"])
        return data


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
