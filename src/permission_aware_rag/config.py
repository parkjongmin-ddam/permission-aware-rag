"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


# Sentinel for the insecure default JWT key. If this value survives into a
# non-development environment, startup fails (see _validate_jwt_secret).
_INSECURE_JWT_DEFAULT = "change-me-in-production"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: str = "development"
    debug: bool = False

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database (used in Stage 2)
    database_url: str = (
        "postgresql://pawrag_user:pawrag_password@localhost:5432/permission_aware_rag"
    )

    # Connection pool sizing. Keep small in deployments that sit behind an
    # external pooler (e.g. Supabase Session pooler) to avoid pooler-on-pooler
    # connection exhaustion. Local dev can use the defaults comfortably.
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10

    # JWT (used in Stage 4)
    # The default is an obvious placeholder. It is allowed only in development;
    # any other environment must set JWT_SECRET_KEY to a 32+ byte random value
    # (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
    jwt_secret_key: str = _INSECURE_JWT_DEFAULT
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Answer generation (M4.2). ANTHROPIC_API_KEY required only for /answer.
    anthropic_api_key: str | None = None

    # LLM backend. Currently Claude API (cloud demo). Air-gapped or
    # API-restricted deployments swap this for an on-prem model (e.g. Ollama
    # ChatOllama serving Qwen2.5 / Llama 3.1). See generation/answerer.py for
    # the single swap point.
    answer_model: str = "claude-sonnet-4-6"
    answer_max_tokens: int = 1024

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        """Refuse to start outside development with a weak or default JWT key."""
        is_dev = self.environment.lower() in {"development", "dev", "local", "test"}
        if is_dev:
            return self

        if self.jwt_secret_key == _INSECURE_JWT_DEFAULT:
            raise ValueError(
                "JWT_SECRET_KEY is still the insecure default. Set a strong "
                "random value in non-development environments "
                '(e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`).'
            )
        if len(self.jwt_secret_key.encode("utf-8")) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 bytes in non-development "
                "environments (HS256 recommendation)."
            )
        return self


settings = Settings()