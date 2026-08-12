from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PLACEHOLDER_MARKERS = ("change-me", "replace-with", "<your", "your-")


def _contains_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(marker in normalized for marker in PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = Field(default="development")
    debug: bool = Field(default=True)
    api_v1_prefix: str = Field(default="/api/v1")
    database_url: str = Field()
    redis_url: str = Field(default="redis://redis:6379/0")
    frontend_origin: str = Field(default="http://localhost:3000")
    backend_public_url: str = Field(default="http://localhost:8000")
    allowed_hosts: str = Field(default="localhost,127.0.0.1,testserver")
    session_secret: str = Field()
    operator_username: str = Field(default="operator")
    operator_password: str = Field()
    max_request_body_bytes: int = Field(default=65536)
    default_jobs_page_size: int = Field(default=24)

    local_artifacts_root: Path = Field(
        default=Path(__file__).resolve().parents[1] / "storage" / "jobs"
    )
    generic_background_music_path: Path = Field(
        default=Path(__file__).resolve().parents[1] / "assets" / "background-music.mp3"
    )

    gemini_api_key: str | None = Field(default=None)
    gemini_model: str = Field(default="gemini-2.5-flash")
    openrouter_api_key: str | None = Field(default=None)
    openrouter_model: str = Field(default="nvidia/nemotron-3-super-120b-a12b:free")
    firecrawl_api_key: str | None = Field(default=None)
    firecrawl_base_url: str = Field(default="https://api.firecrawl.dev")
    groq_api_key: str | None = Field(default=None)
    groq_whisper_model: str = Field(default="whisper-large-v3-turbo")
    pexels_api_key: str | None = Field(default=None)

    whisper_model: str = Field(default="small")
    whisper_device: str = Field(default="auto")
    whisper_compute_type: str = Field(default="int8_float16")
    transcription_max_playlist_items: int = Field(default=200, ge=1, le=200)

    quality_gate_threshold: int = Field(default=7)
    kokoro_voice: str = Field(default="af_heart")
    kokoro_language_code: str = Field(default="a")
    edge_tts_voice: str = Field(default="en-US-EmmaMultilingualNeural")

    youtube_client_secrets_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / "secrets" / "client_secrets.json"
    )
    youtube_privacy_status: str = Field(default="private")
    youtube_default_category_id: str = Field(default="27")
    youtube_refresh_token: str | None = Field(default=None)
    youtube_channel_label: str = Field(default="default")

    @model_validator(mode="after")
    def validate_sensitive_settings(self):
        if _contains_placeholder(self.database_url):
            raise ValueError(
                "DATABASE_URL must be set in .env with a real PostgreSQL password."
            )
        if _contains_placeholder(self.session_secret):
            raise ValueError(
                "SESSION_SECRET must be set in .env to a unique random value."
            )
        if _contains_placeholder(self.operator_password):
            raise ValueError(
                "OPERATOR_PASSWORD must be set in .env to a non-placeholder value."
            )
        return self

    def allowed_hosts_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    def is_production(self) -> bool:
        return self.app_env.lower() == "production"



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.local_artifacts_root = settings.local_artifacts_root.resolve()
    settings.generic_background_music_path = (
        settings.generic_background_music_path.resolve()
    )
    settings.youtube_client_secrets_path = (
        settings.youtube_client_secrets_path.resolve()
    )
    settings.local_artifacts_root.mkdir(parents=True, exist_ok=True)
    return settings
