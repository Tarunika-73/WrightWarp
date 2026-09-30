"""Application configuration loaded from environment variables.

Centralizing settings here means the rest of the codebase never reads
os.environ directly, which keeps configuration testable and mockable.

``.env`` files are resolved by absolute path (repo root first, then
``backend/``, later files overriding earlier ones) rather than relative
to the current working directory - otherwise running ``uvicorn`` or
``pytest`` from ``backend/`` silently ignores the repo-root ``.env`` and
falls back to ``localhost``. Real environment variables (e.g. those set
in the Vercel dashboard) always take precedence over any ``.env`` file.
"""
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "wrightwarp-api"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_user: str | None = None
    mongo_password: str | None = None
    mongo_db_name: str = "wrightwarp"

    # Overrides everything above when set (e.g. for MongoDB Atlas or any
    # connection string that doesn't fit the host/port/user/password shape).
    mongo_uri: str | None = None

    # Comma-separated list of allowed browser origins. The production
    # dashboard is served from the same origin as the API, so this only
    # matters for local development (Vite on :5173) or a separately
    # hosted frontend.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Shared secret for scheduled/administrative endpoints (Vercel Cron
    # sends it as ``Authorization: Bearer <CRON_SECRET>``). When unset,
    # those endpoints refuse every request rather than running unprotected.
    cron_secret: str | None = None

    # Demo mode: enables the SIMULATED demo market source and labels
    # every derived output as DEMO. There is no real, compliance-cleared
    # source yet, so this is on by default.
    demo_mode: bool = True

    # Index base period (calendar year) - index value 100 = average of this year.
    index_base_year: int = 2024

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def mongo_connection_uri(self) -> str:
        if self.mongo_uri:
            return self.mongo_uri
        if self.mongo_user and self.mongo_password:
            # URL-encode credentials: a password containing '@', ':' or '/'
            # would otherwise corrupt the URI. docker-compose creates this
            # user via MONGO_INITDB_ROOT_USERNAME, which always lives in the
            # admin database regardless of mongo_db_name.
            user = quote_plus(self.mongo_user)
            password = quote_plus(self.mongo_password)
            return f"mongodb://{user}:{password}@{self.mongo_host}:{self.mongo_port}/?authSource=admin"
        return f"mongodb://{self.mongo_host}:{self.mongo_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
