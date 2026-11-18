from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8090, ge=1, le=65535)
    api_key: str | None = None
    database_url: str = "sqlite+aiosqlite:///./data/meetbridge.db"

    default_user_name: str = ""
    default_user_email: str = ""
    default_user_location: str = ""
    default_user_timezone: str = "Asia/Kolkata"
    default_bot_display_name: str = "MeetBridge Assistant (Bot)"

    teams_gateway_url: str = ""
    teams_gateway_token: str = ""
    teams_webhook_secret: str = ""
    teams_recording_gateway_enabled: bool = False

    google_oauth_client_file: Path = Path("./secrets/google-oauth-client.json")
    google_token_file: Path = Path("./secrets/google-token.json")
    google_oauth_scopes: str = "https://www.googleapis.com/auth/meetings.space.readonly"

    llm_provider: str = "openai-compatible"
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = "not-required-for-local-server"
    llm_enable_thinking: bool = False

    recording_enabled: bool = False
    recording_root: Path = Path("./data/recordings")
    recording_retention_days: int = Field(default=30, ge=1, le=3650)
    require_recording_consent: bool = True
    transcript_retention_days: int = Field(default=90, ge=1, le=3650)

    @field_validator("api_key")
    @classmethod
    def normalise_api_key(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()

    @property
    def google_scopes(self) -> list[str]:
        return [scope.strip() for scope in self.google_oauth_scopes.split(",") if scope.strip()]

    @property
    def teams_gateway_configured(self) -> bool:
        return bool(self.teams_gateway_url.strip() and self.teams_gateway_token.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
