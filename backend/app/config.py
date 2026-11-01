from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or the project .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="RESEARCHOPS_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # Application
    environment: Literal["development", "production"] = "development"
    cors_origins: CsvList = []

    # Authentication
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=30, ge=1, le=1_440)
    refresh_token_days: int = Field(default=30, ge=1, le=365)
    refresh_reuse_grace_seconds: int = Field(default=30, ge=0, le=300)
    cookie_secure: bool = False
    password_min_length: int = Field(default=8, ge=8, le=64)
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_lock_minutes: int = Field(default=15, ge=1, le=1_440)

    # Storage
    auth_db_path: Path = Path("data/auth.db")
    research_db_path: Path = Path("data/research.db")
    report_dir: Path = Path("data/reports")

    # Credits
    user_credits: int = Field(default=5, ge=0)
    research_credit_cost: int = Field(default=1, ge=0)
    max_reports_per_run: int = Field(default=3, ge=1, le=50)

    # Reports
    default_report_pages: int = Field(default=5, ge=1, le=50)
    max_report_pages: int = Field(default=20, ge=1, le=50)
    report_llm_timeout_seconds: int = Field(default=120, ge=10, le=900)
    report_token_budget: int = Field(default=300_000, ge=1_000, le=5_000_000)
    report_max_runtime_seconds: int = Field(default=420, ge=30, le=1_800)

    # Models
    primary_model: str = "nebius:nvidia/Nemotron-3_5-Lightning"
    fallback_models: CsvList = ["gemini:gemini-3.8-flash"]
    extra_models: CsvList = ["nebius:openai/gpt-oss-120b", "openai:gpt-4.1"]
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    llm_timeout_seconds: int = Field(default=60, ge=5, le=600)

    # API keys use the providers' conventional, unprefixed names.
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    nebius_api_key: SecretStr | None = Field(default=None, validation_alias="NEBIUS_API_KEY")
    tavily_api_key: SecretStr | None = Field(default=None, validation_alias="TAVILY_API_KEY")
    langsmith_api_key: SecretStr | None = Field(default=None, validation_alias="LANGSMITH_API_KEY")

    # Tracing
    langsmith_tracing: bool = False
    langsmith_project: str = "researchops"

    # Research guardrails
    max_question_chars: int = Field(default=2_000, ge=50, le=20_000)
    max_searches: int = Field(default=8, ge=1, le=100)
    max_sources: int = Field(default=15, ge=1, le=500)
    max_pages: int = Field(default=10, ge=1, le=100)
    max_iterations: int = Field(default=5, ge=1, le=20)
    max_token_budget: int = Field(default=100_000, ge=1_000, le=2_000_000)
    max_runtime_seconds: int = Field(default=240, ge=10, le=3_600)
    max_sources_per_domain: int = Field(default=3, ge=1, le=50)
    max_chars_per_source: int = Field(default=6_000, ge=500, le=100_000)
    fetch_timeout_seconds: int = Field(default=10, ge=1, le=120)
    max_fetch_bytes: int = Field(default=3_000_000, ge=10_000, le=50_000_000)

    @field_validator("cors_origins", "fallback_models", "extra_models", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "openai_api_key", "gemini_api_key", "nebius_api_key", "tavily_api_key", "langsmith_api_key", mode="before"
    )
    @classmethod
    def _blank_key_is_missing(cls, value: object) -> object:
        return value or None

    @field_validator("auth_db_path", "research_db_path", "report_dir")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @model_validator(mode="after")
    def _require_secure_cookie_in_production(self) -> "Settings":
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("RESEARCHOPS_COOKIE_SECURE must be true in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings instance for the application process."""
    return Settings()
