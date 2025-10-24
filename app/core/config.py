"""Application settings and security-related configuration options."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    # App
    app_env: str = Field(default="dev")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    log_format: Literal["json", "plain"] = Field(default="json")

    # DB & Retrieval
    db_path: str = Field(default=str(BASE_DIR / "db" / "app_data.sqlite"))
    index_path: str = Field(default=str(BASE_DIR / "data" / "faiss_index"))
    embed_model: str = Field(default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    # Retrieval thresholds
    min_vector_score: float = Field(default=0.30)   # cosine/IP score threshold
    max_ctx_items: int = Field(default=4)           # top-k to send to LLM
    max_desc_chars: int = Field(default=220)        # truncate description per item

    # LLM Provider chain (failover)
    llm_provider: str = Field(default="openrouter")  # openrouter|huggingface|none
    llm_api_base: str = Field(default="")            # set by env
    llm_api_key: str = Field(default="")             # secret
    llm_model: str = Field(default="")
    hf_api_base: str = Field(default="")             # optional second provider (HF)
    hf_api_key: str = Field(default="")              # optional
    hf_model: str = Field(default="")                # optional

    # Security
    auth_mode: Literal["api_key", "jwt"] = Field(default="api_key")
    require_api_key: bool = Field(default=False)
    api_key: str = Field(
        default="", description="Static API key fallback when persistent keys are unavailable."
    )
    hmac_required: bool = Field(default=False)
    hmac_window_sec: int = Field(default=300)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8000"])
    security_headers_enabled: bool = Field(default=True)
    max_request_body_bytes: int = Field(default=65_536)
    debug_routes: bool = Field(default=True)

    # Rate-limiting (token bucket)
    rl_bucket_size: int = Field(default=60)            # tokens per window
    rl_refill_per_sec: float = Field(default=1.0)      # refill rate
    rl_identity_header: str = Field(default="X-API-Key")  # or "ip"

    # HTTP timeouts/retries
    llm_timeout_s: int = Field(default=60)
    llm_retries: int = Field(default=2)                # per provider

    # JWT (only used when auth_mode == "jwt")
    jwt_signing_key: str | None = Field(default=None)
    jwt_public_key: str | None = Field(default=None)
    jwt_kid: str = Field(default="main")
    jwt_iss: str = Field(default="rag-instabot")
    jwt_aud: str = Field(default="rag-clients")
    access_ttl_min: int = Field(default=10)
    refresh_ttl_days: int = Field(default=7)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items or ["http://localhost:8000"]
        return value

    @model_validator(mode="after")
    def _validate_auth(self) -> "Settings":
        if self.auth_mode not in {"api_key", "jwt"}:
            raise ValueError("AUTH_MODE must be 'api_key' or 'jwt'")
        if self.auth_mode == "jwt":
            if not self.jwt_signing_key and not self.jwt_public_key:
                raise ValueError("JWT mode requires JWT_SIGNING_KEY or JWT_PUBLIC_KEY")
        if self.require_api_key and not self.api_key:
            # static fallback must be present when explicitly required
            raise ValueError("REQUIRE_API_KEY is true but API_KEY not configured")
        if self.max_request_body_bytes <= 0:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be positive")
        return self


settings = Settings()
